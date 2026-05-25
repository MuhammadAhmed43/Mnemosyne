"""Data access for conflict_events (Doc 07 §2.4, Doc 05).

Maps the ConflictCandidate model onto the conflict_events table. The model's
`suggested_strategy` is stored in `resolution_strategy`, and `auto_resolvable`
in `auto_resolved`. Resolution updates the same row in place.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.models.conflict import ConflictCandidate, ResolutionEvent
from backend.models.enums import ConflictStrategy, ConflictType, ResolutionStatus
from backend.repositories._serde import ser
from backend.utils.time import now_utc


def row_to_candidate(row: sqlite3.Row) -> ConflictCandidate:
    d = dict(row)
    return ConflictCandidate(
        id=d["id"],
        workspace_id=d["workspace_id"],
        node_a_id=d["node_a_id"],
        node_b_id=d["node_b_id"],
        conflict_type=ConflictType(d["conflict_type"]),
        similarity_score=d.get("similarity_score") or 0.0,
        contradiction_score=d.get("contradiction_score") or 0.0,
        suggested_strategy=ConflictStrategy(d["resolution_strategy"])
        if d.get("resolution_strategy")
        else ConflictStrategy.USER_REVIEW,
        auto_resolvable=bool(d.get("auto_resolved")),
        status=ResolutionStatus(d.get("status") or "pending"),
        detected_at=d["detected_at"],
    )


class ConflictRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, c: ConflictCandidate) -> ConflictCandidate:
        self.conn.execute(
            "INSERT INTO conflict_events (id, workspace_id, node_a_id, node_b_id, "
            "conflict_type, similarity_score, contradiction_score, status, "
            "resolution_strategy, auto_resolved, detected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                c.id, c.workspace_id, c.node_a_id, c.node_b_id,
                ser(c.conflict_type), c.similarity_score, c.contradiction_score,
                ser(c.status), ser(c.suggested_strategy), int(c.auto_resolvable),
                ser(c.detected_at),
            ),
        )
        self.conn.commit()
        return c

    def get(self, conflict_id: str) -> Optional[ConflictCandidate]:
        row = self.conn.execute(
            "SELECT * FROM conflict_events WHERE id=?", (conflict_id,)
        ).fetchone()
        return row_to_candidate(row) if row else None

    def get_pending(self, workspace_id: str) -> list[ConflictCandidate]:
        rows = self.conn.execute(
            "SELECT * FROM conflict_events WHERE workspace_id=? AND status=? "
            "ORDER BY detected_at DESC",
            (workspace_id, ResolutionStatus.PENDING.value),
        ).fetchall()
        return [row_to_candidate(r) for r in rows]

    def get_all(self, workspace_id: str) -> list[ConflictCandidate]:
        rows = self.conn.execute(
            "SELECT * FROM conflict_events WHERE workspace_id=? ORDER BY detected_at DESC",
            (workspace_id,),
        ).fetchall()
        return [row_to_candidate(r) for r in rows]

    def resolve(self, conflict_id: str, event: ResolutionEvent) -> None:
        self.conn.execute(
            "UPDATE conflict_events SET status=?, resolution_strategy=?, "
            "winning_node_id=?, archived_node_ids=?, auto_resolved=?, "
            "resolved_by_user=?, evidence=?, confidence=?, resolved_at=? WHERE id=?",
            (
                ser(event.status), ser(event.strategy_used), event.winning_node_id,
                json.dumps(event.archived_node_ids),
                int(event.resolved_by == "system"),
                None if event.resolved_by == "system" else event.resolved_by,
                event.evidence, event.confidence, ser(now_utc()), conflict_id,
            ),
        )
        self.conn.commit()
