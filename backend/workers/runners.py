"""Background worker loops (Doc 10 §7, Doc 16). All DB work is sync, so the
per-item commit blocks run in a thread to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from backend.container import ServiceContainer
from backend.extraction.pipeline import _strip_injected_context
from backend.models.capture import CaptureRecord
from backend.models.conflict import ConflictCandidate
from backend.models.enums import ConflictStrategy, ConflictType, NodeType
from backend.models.extraction import ExtractionCandidate, PendingReview
from backend.utils.time import now_utc
from backend.workers.queue import DiskBackedQueue

logger = logging.getLogger("mnemosyne.workers")
PENDING_TTL_DAYS = 7
MAX_RETRIES = 3


def _commit_results(container: ServiceContainer, record: CaptureRecord, result, ws: str) -> dict:
    """Sync: commit auto candidates into workspace `ws`, detect/resolve conflicts,
    queue pending. `ws` is the LLM-resolved workspace (may differ from the
    provisional one on the record)."""
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


def _coerce_type(value: object, default: NodeType = NodeType.USER_NOTE) -> NodeType:
    try:
        return NodeType(str(value or "").strip().lower())
    except ValueError:
        return default


def _existing_memories(container: ServiceContainer, ws: str) -> list[dict]:
    """Compact view of the workspace's active memories for the reconcile prompt."""
    return [
        {"id": n.id, "type": n.node_type.value, "content": n.content}
        for n in container.node_repo(ws).get_active(ws, limit=40)
    ]


def _apply_memory_diff(container: ServiceContainer, record: CaptureRecord, ws: str, diff: dict) -> dict:
    """Apply the model's memory diff: add new nodes, enrich (versioned) existing
    ones, supersede changed decisions, and mark goals/tasks complete."""
    graph = container.graph_service(ws)
    conflict = container.conflict_service(ws)
    conflict_repo = container.conflict_repo(ws)
    nodes = container.node_repo(ws)
    thread_repo = container.thread_repo(ws)
    thread = thread_repo.get_or_create(record.session_id, ws, record.platform.value)

    def _check_conflicts(node) -> None:
        for c in conflict.detect_conflicts(ws, node):
            conflict_repo.create(c)
            if c.auto_resolvable:
                ev = conflict.auto_resolve(c)
                if ev:
                    conflict_repo.resolve(c.id, ev)

    added = updated = superseded = completed = 0

    for item in diff.get("add") or []:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        cand = ExtractionCandidate(
            node_type=_coerce_type(item.get("type")), content=content,
            structured_data=item.get("structured_data") or {}, confidence=0.9,
            source_pass="llm_reconcile", evidence="",
        )
        node = graph.commit_node(ws, cand, record.session_id, record.platform)
        thread_repo.add_node(thread.id, node.id, thread.turn_count)
        added += 1
        _check_conflicts(node)

    for item in diff.get("update") or []:
        nid, content = item.get("id"), (item.get("content") or "").strip()
        if not nid or not content or nodes.get(nid) is None:
            continue
        graph.update_node_content(nid, ws, content, changed_by="system", reason=(item.get("reason") or "elaborated"))
        updated += 1

    for item in diff.get("supersede") or []:
        nid, content = item.get("id"), (item.get("content") or "").strip()
        old = nodes.get(nid) if nid else None
        if old is None or not content:
            continue
        cand = ExtractionCandidate(
            node_type=_coerce_type(item.get("type"), old.node_type), content=content,
            structured_data={}, confidence=0.9, source_pass="llm_reconcile", evidence="",
        )
        new_node = graph.commit_node(ws, cand, record.session_id, record.platform)
        thread_repo.add_node(thread.id, new_node.id, thread.turn_count)
        if new_node.id != old.id:
            # Option B: surface a PENDING "Changed plan" conflict — keep BOTH the
            # old and new memory active and let the user decide (Keep old / Keep new
            # / Both). Resolving it supersedes the loser; until then memory holds
            # both, and the change is visible on the Conflicts page.
            conflict_repo.create(ConflictCandidate(
                workspace_id=ws, node_a_id=old.id, node_b_id=new_node.id,
                conflict_type=ConflictType.VERSION_FORK, contradiction_score=0.85,
                suggested_strategy=ConflictStrategy.TEMPORAL, auto_resolvable=False,
            ))
        superseded += 1

    for item in diff.get("complete") or []:
        nid = item.get("id")
        old = nodes.get(nid) if nid else None
        if old is None:
            continue
        sd = {**(old.structured_data or {}), "status": "COMPLETED", "completed_at": now_utc().isoformat()}
        nodes.update_fields(old.id, structured_data=sd)
        completed += 1

    # Global about-me facts (cross-project), de-duplicated.
    try:
        prof = container.profile_repo()
        for item in diff.get("profile") or []:
            content = (item.get("content") or "").strip()
            if content and not prof.exists_similar(content):
                prof.add(content, kind="fact", source="model")
    except Exception:  # noqa: BLE001 — profile is best-effort
        pass

    return {
        "committed": added + superseded, "pending": 0,
        "added": added, "updated": updated, "superseded": superseded, "completed": completed,
    }


async def _resolve_workspace(container: ServiceContainer, record: CaptureRecord, settings) -> str:
    """Pick the workspace for a turn.

    The LLM is the authoritative router (qwen reasons over the turn + all
    workspaces). It is biased to KEEP the conversation in the workspace it's
    currently bound to, so it doesn't flip mid-project — but it WILL split a
    genuinely different project into its own workspace, which is what stops
    distinct topics bleeding together. Name-dedup prevents duplicate workspaces.
    When the model is unavailable, fall back to the content-aware capture-time
    routing on `record.workspace_id`."""
    provisional = record.workspace_id
    if not settings.llm_extraction_enabled:
        return provisional
    # Fast path: an already-bound conversation stays in its workspace WITHOUT a
    # routing LLM call. Capture-time routing (new-project detection + fit-checked
    # URL pin) already splits a genuine topic change into a new workspace and
    # repins the URL, so `provisional` is correct here. This halves per-turn LLM
    # work for ongoing chats (only reconcile runs); the routing call is reserved
    # for the FIRST turn of a new chat (unbound), where the split decision matters.
    if record.tab_url and container.workspace_service.url_mapping(record.tab_url):
        return provisional
    llm = container.pipeline.llm
    if not await llm.is_available():
        return provisional  # offline: trust the content-aware capture-time routing
    active = container.workspace_service.list(status="active")
    ids = {w.id for w in active}
    current_id = provisional if provisional in ids else ""
    decision = await llm.route_workspace(
        record.user_message, record.ai_response,
        [{"id": w.id, "name": w.name, "summary": (w.summary_text or w.description or "")} for w in active],
        current_id=current_id,
    )
    match = (decision.get("match_id") or "").strip()
    new_name = (decision.get("new_name") or "").strip()
    chosen = current_id or provisional
    if match in ids:
        chosen = match
    elif new_name:
        # New topic -> new workspace, BUT dedup by name: a weak model proposes the
        # same new_name on every turn, which previously spawned a pile of
        # identically-named workspaces. If one already exists, reuse it.
        existing = next((w for w in active if w.name.strip().lower() == new_name.strip().lower()), None)
        if existing:
            chosen = existing.id
        else:
            try:
                ws = container.workspace_service.create(
                    name=new_name[:40], description=f"Auto-created from a {record.platform.value} conversation", icon="✨")
                container.workspace_repo.update_fields(
                    ws.id, summary_text=f"{record.user_message} {record.ai_response}".strip()[:500])
                chosen = ws.id
            except Exception:  # noqa: BLE001 — e.g. max workspaces reached
                chosen = provisional
    # If we routed away from a workspace ingest auto-created (now empty), drop it.
    if chosen != provisional and record.workspace_autocreated:
        try:
            if container.node_repo(provisional).count(provisional) == 0:
                container.workspace_service.delete(provisional)
        except Exception:  # noqa: BLE001
            pass
    if record.tab_url and chosen:
        try:
            container.workspace_service.remember_mapping(record.platform.value, chosen, record.tab_url)
        except Exception:  # noqa: BLE001
            pass
    return chosen


async def extraction_worker(container: ServiceContainer, queue: DiskBackedQueue) -> None:
    while True:
        record = await queue.get()
        try:
            prov = container.workspace_service.get(record.workspace_id)
            summary = prov.summary_text if prov else ""
            settings = container.settings_repo.get_user_settings()
            # Cheap pass: safety gates (sensitive/trivial) + rule/NER fallback
            # candidates. The LLM's real work happens in reconcile (one call), so we
            # skip the LLM extract pass here to avoid a wasted second inference.
            result = await container.pipeline.run(
                record,
                workspace_summary=summary or "",
                blocked_terms=settings.custom_blocked_terms,
                auto_commit_threshold=settings.auto_commit_threshold,
                min_confidence=settings.min_confidence,
                llm_enabled=False,
            )
            # LLM is the primary router; embedding/rule provisional is the fallback.
            ws_id = await _resolve_workspace(container, record, settings)
            # Memory-diff brain: when the model is available and this turn passed the
            # gates, let it reconcile the turn against the workspace's existing
            # memories (add / update / supersede / complete). Falls back to the
            # rule/NER candidates when the model is unavailable.
            diff = None
            if not result.skipped and settings.llm_extraction_enabled and await container.pipeline.llm.is_available():
                existing = await asyncio.to_thread(_existing_memories, container, ws_id)
                diff = await container.pipeline.llm.reconcile_memories(
                    _strip_injected_context(record.user_message), record.ai_response, existing, summary or "",
                )
            if diff is not None:
                stats = await asyncio.to_thread(_apply_memory_diff, container, record, ws_id, diff)
            else:
                stats = await asyncio.to_thread(_commit_results, container, record, result, ws_id)
            queue.mark_complete(record.id)
            final = container.workspace_service.get(ws_id)
            await container.events.put({
                "event": "extraction_completed",
                "workspace_id": ws_id,
                "workspace_name": final.name if final else "",
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
