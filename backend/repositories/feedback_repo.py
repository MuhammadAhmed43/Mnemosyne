"""Extraction feedback storage (Plan 12 §5)."""

from __future__ import annotations

import sqlite3
from typing import Optional

from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class FeedbackRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        node_id: Optional[str],
        action: str,
        original_type: Optional[str],
        original_confidence: Optional[float],
        corrected_type: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO extraction_feedback (id, node_id, action, original_type, "
            "original_confidence, corrected_type, timestamp) VALUES (?,?,?,?,?,?,?)",
            (generate_id("fb"), node_id, action, original_type, original_confidence,
             corrected_type, now_utc().isoformat()),
        )
        self.conn.commit()

    def get_stats(self) -> dict[str, dict[str, int]]:
        rows = self.conn.execute(
            "SELECT original_type, action, COUNT(*) c FROM extraction_feedback "
            "GROUP BY original_type, action"
        ).fetchall()
        stats: dict[str, dict[str, int]] = {}
        for r in rows:
            t = r["original_type"] or "unknown"
            stats.setdefault(t, {"total": 0, "approved": 0, "edited": 0, "rejected": 0})
            stats[t][r["action"]] = stats[t].get(r["action"], 0) + r["c"]
            stats[t]["total"] += r["c"]
        return stats
