"""Global DB initialization + default settings seeding (Doc 07 §3.2)."""

from __future__ import annotations

import sqlite3

from backend.db.migrations import run_global_migrations
from backend.utils.time import now_utc

DEFAULT_SETTINGS = {
    "capture_enabled": "true",
    "auto_commit_threshold": "0.80",
    "min_confidence": "0.60",
    "llm_extraction_enabled": "true",
    "local_model": "phi4-mini",
    "embedding_model": "bge-m3",
    "context_token_budget": "2000",
    "decay_enabled": "true",
    "decay_schedule_hours": "6",
    "pending_review_expiry_days": "7",
    "sensitive_data_filter": "true",
    "cloud_sync_enabled": "false",
    "theme": "dark",
    "sidebar_position": "right",
}


def init_global_db(conn: sqlite3.Connection) -> None:
    run_global_migrations(conn)
    now = now_utc().isoformat()
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
    conn.commit()
