"""Global 'about me' memory — who the user is / how they work. Stored in the
global DB (cross-project) and injected into every chat alongside the brief."""

from __future__ import annotations

import sqlite3
import uuid

from backend.utils.time import now_utc


class ProfileRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, content, kind, source, pinned, created_at, updated_at "
            "FROM profile_memories ORDER BY pinned DESC, updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def add(self, content: str, kind: str = "fact", source: str = "user") -> dict:
        now = now_utc().isoformat()
        pid = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO profile_memories(id, content, kind, source, pinned, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?)",
            (pid, content, kind, source, now, now),
        )
        self.conn.commit()
        return {"id": pid, "content": content, "kind": kind, "source": source, "pinned": 0,
                "created_at": now, "updated_at": now}

    def update(self, pid: str, content: str) -> None:
        self.conn.execute(
            "UPDATE profile_memories SET content=?, updated_at=? WHERE id=?",
            (content, now_utc().isoformat(), pid),
        )
        self.conn.commit()

    def delete(self, pid: str) -> None:
        self.conn.execute("DELETE FROM profile_memories WHERE id=?", (pid,))
        self.conn.commit()

    def exists_similar(self, content: str) -> bool:
        """Cheap dedup so the model doesn't re-add the same about-me fact each turn."""
        row = self.conn.execute(
            "SELECT 1 FROM profile_memories WHERE lower(trim(content))=lower(trim(?)) LIMIT 1",
            (content,),
        ).fetchone()
        return row is not None

    def as_context_lines(self, limit: int = 20) -> list[str]:
        return [r["content"] for r in self.list()[:limit]]
