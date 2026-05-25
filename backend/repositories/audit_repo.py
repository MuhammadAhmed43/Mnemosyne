"""Append-only, hash-chained audit log (Doc 13 §8). Tamper-evident."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Optional

from backend.utils.ids import generate_id
from backend.utils.time import now_utc

_GENESIS = "0" * 64


class AuditRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _last_hash(self) -> str:
        row = self.conn.execute(
            "SELECT chain_hash FROM audit_log ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else _GENESIS

    @staticmethod
    def _hash(prev: str, timestamp: str, action: str, entity_id: Optional[str]) -> str:
        return hashlib.sha256(f"{prev}{timestamp}{action}{entity_id or ''}".encode()).hexdigest()

    def append(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> str:
        ts = now_utc().isoformat()
        chain_hash = self._hash(self._last_hash(), ts, action, entity_id)
        entry_id = generate_id("aud")
        self.conn.execute(
            "INSERT INTO audit_log (id, timestamp, action, entity_type, entity_id, "
            "workspace_id, details, chain_hash) VALUES (?,?,?,?,?,?,?,?)",
            (entry_id, ts, action, entity_type, entity_id, workspace_id,
             json.dumps(details or {}), chain_hash),
        )
        self.conn.commit()
        return entry_id

    def get_log(self, workspace_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        if workspace_id:
            rows = self.conn.execute(
                "SELECT * FROM audit_log WHERE workspace_id=? ORDER BY timestamp DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def verify_integrity(self) -> bool:
        """Recompute the chain in insertion order; any tampering breaks it."""
        prev = _GENESIS
        for r in self.conn.execute(
            "SELECT timestamp, action, entity_id, chain_hash FROM audit_log ORDER BY rowid"
        ):
            expected = self._hash(prev, r["timestamp"], r["action"], r["entity_id"])
            if expected != r["chain_hash"]:
                return False
            prev = r["chain_hash"]
        return True
