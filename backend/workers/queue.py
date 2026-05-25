"""Disk-backed async capture queue for crash recovery (Doc 03 §7, Doc 16 §5.4).

Each push is journaled to JSONL before enqueue; completions append a done-marker.
On startup, replay re-enqueues records that were journaled but not completed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from backend.models.capture import CaptureRecord

logger = logging.getLogger("mnemosyne.queue")


class DiskBackedQueue:
    def __init__(self, journal_path: Path, max_size: int = 100):
        self._queue: asyncio.Queue[CaptureRecord] = asyncio.Queue(maxsize=max_size)
        self._journal = journal_path
        self._journal.parent.mkdir(parents=True, exist_ok=True)

    async def push(self, record: CaptureRecord) -> None:
        with self._journal.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        await self._queue.put(record)

    async def get(self) -> CaptureRecord:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def mark_complete(self, capture_id: str) -> None:
        with self._journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"_done": capture_id}) + "\n")

    def qsize(self) -> int:
        return self._queue.qsize()

    async def replay_unprocessed(self) -> int:
        if not self._journal.exists():
            return 0
        pushed: dict[str, CaptureRecord] = {}
        done: set[str] = set()
        for line in self._journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if "_done" in obj:
                done.add(obj["_done"])
            else:
                rec = CaptureRecord.model_validate(obj)
                pushed[rec.id] = rec
        pending = [r for rid, r in pushed.items() if rid not in done]
        for rec in pending:
            await self._queue.put(rec)
        logger.info("recovery: replayed %d unprocessed captures", len(pending))
        return len(pending)

    def compact(self) -> None:
        """Rewrite journal keeping only still-pending records (call on clean shutdown)."""
        if not self._journal.exists():
            return
        pushed: dict[str, CaptureRecord] = {}
        done: set[str] = set()
        for line in self._journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if "_done" in obj:
                done.add(obj["_done"])
            else:
                rec = CaptureRecord.model_validate(obj)
                pushed[rec.id] = rec
        remaining = [r for rid, r in pushed.items() if rid not in done]
        with self._journal.open("w", encoding="utf-8") as f:
            for rec in remaining:
                f.write(rec.model_dump_json() + "\n")
