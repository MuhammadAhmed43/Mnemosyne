"""Data access for onboarding_state + onboarding_events (Doc 17 §14)."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class OnboardingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_state(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM onboarding_state WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO onboarding_state(key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_utc().isoformat()),
        )
        self.conn.commit()

    def log_event(self, event_type: str, metadata: Optional[dict] = None) -> str:
        event_id = generate_id("onb")
        self.conn.execute(
            "INSERT INTO onboarding_events(id, event_type, metadata, timestamp) VALUES (?,?,?,?)",
            (event_id, event_type, json.dumps(metadata or {}), now_utc().isoformat()),
        )
        self.conn.commit()
        return event_id

    def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> list[dict]:
        if event_type:
            rows = self.conn.execute(
                "SELECT * FROM onboarding_events WHERE event_type=? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM onboarding_events ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
