"""Data access for sessions (Doc 07 §2.6)."""

from __future__ import annotations

import sqlite3
from typing import Optional

from backend.utils.time import now_utc

_COUNTERS = {"turn_count", "capture_count", "extraction_count", "nodes_extracted", "nodes_pending"}


class SessionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(
        self, workspace_id: str, session_id: str, platform: str, tab_url: Optional[str] = None
    ) -> str:
        existing = self.conn.execute(
            "SELECT id FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if existing:
            return session_id
        self.conn.execute(
            "INSERT INTO sessions (id, workspace_id, platform, tab_url, started_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, workspace_id, platform, tab_url, now_utc().isoformat()),
        )
        self.conn.commit()
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def increment(self, session_id: str, **counters: int) -> None:
        cols = {k: v for k, v in counters.items() if k in _COUNTERS}
        if not cols:
            return
        sets = ",".join(f"{c} = {c} + ?" for c in cols)
        self.conn.execute(
            f"UPDATE sessions SET {sets} WHERE id=?", [*cols.values(), session_id]
        )
        self.conn.commit()

    def end_session(self, session_id: str, snapshot: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE sessions SET ended_at=?, working_memory_snapshot=? WHERE id=?",
            (now_utc().isoformat(), snapshot, session_id),
        )
        self.conn.commit()

    def recent(self, workspace_id: str, limit: int = 3) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE workspace_id=? ORDER BY started_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
