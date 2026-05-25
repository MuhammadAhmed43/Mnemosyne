"""Background worker loops (Doc 10 §7, Doc 16). All DB work is sync, so the
per-item commit blocks run in a thread to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from backend.container import ServiceContainer
from backend.models.capture import CaptureRecord
from backend.models.extraction import PendingReview
from backend.utils.time import now_utc
from backend.workers.queue import DiskBackedQueue

logger = logging.getLogger("mnemosyne.workers")
PENDING_TTL_DAYS = 7
MAX_RETRIES = 3


def _commit_results(container: ServiceContainer, record: CaptureRecord, result) -> dict:
    """Sync: commit auto candidates, detect/resolve conflicts, queue pending."""
    ws = record.workspace_id
    graph = container.graph_service(ws)
    conflict = container.conflict_service(ws)
    conflict_repo = container.conflict_repo(ws)
    pending_repo = container.pending_repo(ws)

    # Plan 12 §1: link extracted nodes into this session's conversation thread.
    thread_repo = container.thread_repo(ws)
    thread = thread_repo.get_or_create(record.session_id, ws, record.platform.value)

    committed = 0
    for cand in result.to_commit:
        node = graph.commit_node(ws, cand, record.session_id, record.platform)
        thread_repo.add_node(thread.id, node.id, thread.turn_count)
        committed += 1
        for c in conflict.detect_conflicts(ws, node):
            conflict_repo.create(c)
            if c.auto_resolvable:
                ev = conflict.auto_resolve(c)
                if ev:
                    conflict_repo.resolve(c.id, ev)

    expires = now_utc() + timedelta(days=PENDING_TTL_DAYS)
    src = f"{record.user_message[:120]} / {record.ai_response[:120]}"
    # Dedup pending against existing pending items AND already-committed nodes, so
    # the same low-confidence candidate seen across turns doesn't pile up.
    seen = {(p.candidate_type, p.candidate_content.strip().lower()) for p in pending_repo.get_pending(ws)}
    pending_added = 0
    for cand in result.pending_review:
        key = (cand.node_type.value, cand.content.strip().lower())
        if key in seen:
            continue
        if graph.nodes.find_active_duplicate(ws, cand.node_type, cand.content) is not None:
            continue  # already committed -> no need to review a duplicate
        seen.add(key)
        pending_repo.create(PendingReview(
            workspace_id=ws, candidate_type=cand.node_type.value,
            candidate_content=cand.content, candidate_data=cand.structured_data,
            candidate_confidence=cand.confidence, source_session_id=record.session_id,
            source_platform=record.platform.value, source_context=src, expires_at=expires,
        ))
        pending_added += 1
    return {"committed": committed, "pending": pending_added}


async def extraction_worker(container: ServiceContainer, queue: DiskBackedQueue) -> None:
    while True:
        record = await queue.get()
        try:
            ws = container.workspace_service.get(record.workspace_id)
            summary = ws.summary_text if ws else ""
            # Read live routing thresholds from user settings so the Settings
            # sliders actually govern auto-commit vs pending (they used to be
            # hardcoded in the scorer and ignored).
            settings = container.settings_repo.get_user_settings()
            result = await container.pipeline.run(
                record,
                workspace_summary=summary or "",
                blocked_terms=settings.custom_blocked_terms,
                auto_commit_threshold=settings.auto_commit_threshold,
                min_confidence=settings.min_confidence,
                llm_enabled=settings.llm_extraction_enabled,
            )
            stats = await asyncio.to_thread(_commit_results, container, record, result)
            queue.mark_complete(record.id)
            await container.events.put({
                "event": "extraction_completed", "workspace_id": record.workspace_id,
                "nodes_committed": stats["committed"], "nodes_pending": stats["pending"],
            })
        except Exception as e:  # noqa: BLE001
            logger.error("extraction failed for %s: %s", record.id, type(e).__name__)
            record.retry_count += 1
            if record.retry_count < MAX_RETRIES:
                await asyncio.sleep(2 ** record.retry_count)
                await queue.push(record)
        finally:
            queue.task_done()


async def decay_worker(container: ServiceContainer) -> None:
    while True:
        await asyncio.sleep(container.config.decay_interval_hours * 3600)
        for ws in await asyncio.to_thread(container.workspace_repo.get_active):
            await asyncio.to_thread(container.decay_service(ws.id).run_decay_cycle, ws.id)
        await container.events.put({"event": "decay_completed"})


async def consolidation_worker(container: ServiceContainer) -> None:
    while True:
        await asyncio.sleep(_seconds_until_hour(container.config.consolidation_hour))
        for ws in await asyncio.to_thread(container.workspace_repo.get_active):
            await asyncio.to_thread(container.consolidation_service(ws.id).run_consolidation, ws.id)


async def cleanup_worker(container: ServiceContainer) -> None:
    while True:
        await asyncio.sleep(3600)
        for ws in await asyncio.to_thread(container.workspace_repo.get_active):
            await asyncio.to_thread(container.pending_repo(ws.id).expire_old)


async def backup_worker(container: ServiceContainer) -> None:
    import sqlite3

    while True:
        await asyncio.sleep(_seconds_until_hour(2))
        backup_dir = container.config.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_utc().strftime("%Y%m%d")
        for ws in await asyncio.to_thread(container.workspace_repo.get_active):
            src = container.config.data_dir / "workspaces" / ws.id / "graph.db"
            if not src.exists():
                continue
            dst = backup_dir / f"{ws.id}_{stamp}.db"
            await asyncio.to_thread(_backup_db, src, dst)
        cutoff = now_utc() - timedelta(days=container.config.backup_retention_days)
        for f in backup_dir.glob("*.db"):
            if datetime.utcfromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()


def _backup_db(src, dst) -> None:
    import sqlite3

    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    d.close()
    s.close()


def _seconds_until_hour(hour: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()
