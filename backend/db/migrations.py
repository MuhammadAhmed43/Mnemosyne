"""Sequential migration runner for global.db (Doc 07 §5).

The full schema is created idempotently (IF NOT EXISTS) via schema.py; this
records baseline + applies any future incremental migrations in order.
"""

from __future__ import annotations

import sqlite3

from backend.db.schema import create_global_schema
from backend.utils.time import now_utc

# (version, name) baseline. Future migrations append (version, name, fn) below.
_BASELINE = (1, "001_initial_global")


def _record(conn: sqlite3.Connection, version: int, name: str) -> None:
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    if version not in applied:
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, now_utc().isoformat()),
        )


def run_global_migrations(conn: sqlite3.Connection) -> None:
    create_global_schema(conn)  # idempotent; also creates schema_migrations
    _record(conn, *_BASELINE)
    # Future incremental migrations go here:
    #   if 2 not in applied: alter_something(conn); _record(conn, 2, "002_...")
    conn.commit()
