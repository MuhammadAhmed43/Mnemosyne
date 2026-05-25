"""Typed UserSettings over the global KV settings table (Doc 07 §3.2).

Each UserSettings field is stored JSON-encoded under a key matching the field
name, so round-trips preserve types cleanly. Missing keys fall back to the
UserSettings defaults.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.models.settings import UserSettings
from backend.utils.time import now_utc


class SettingsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_raw(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_raw(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_utc().isoformat()),
        )
        self.conn.commit()

    def get_user_settings(self) -> UserSettings:
        stored = {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM settings")}
        data: dict[str, object] = {}
        for field in UserSettings.model_fields:
            if field in stored:
                try:
                    data[field] = json.loads(stored[field])
                except (json.JSONDecodeError, ValueError):
                    pass  # legacy/plain values ignored; default used
        return UserSettings(**data)

    def save_user_settings(self, settings: UserSettings) -> None:
        for field, value in settings.model_dump(mode="json").items():
            self.set_raw(field, json.dumps(value))
