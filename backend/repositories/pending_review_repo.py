"""Data access for pending_reviews (Doc 07 §2.5)."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.models.extraction import PendingReview
from backend.repositories._serde import ser
from backend.utils.time import now_utc

_COLUMNS = [
    "id", "workspace_id", "candidate_type", "candidate_content", "candidate_data",
    "candidate_confidence", "source_session_id", "source_platform", "source_context",
    "created_at", "expires_at", "status", "reviewed_at", "review_action",
]


def row_to_review(row: sqlite3.Row) -> PendingReview:
    d = dict(row)
    d["candidate_data"] = json.loads(d.get("candidate_data") or "{}")
    return PendingReview(**d)


class PendingReviewRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, review: PendingReview) -> PendingReview:
        self.conn.execute(
            f"INSERT INTO pending_reviews ({','.join(_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(_COLUMNS))})",
            [ser(getattr(review, c)) for c in _COLUMNS],
        )
        self.conn.commit()
        return review

    def get(self, review_id: str) -> Optional[PendingReview]:
        row = self.conn.execute(
            "SELECT * FROM pending_reviews WHERE id=?", (review_id,)
        ).fetchone()
        return row_to_review(row) if row else None

    def get_pending(self, workspace_id: str) -> list[PendingReview]:
        rows = self.conn.execute(
            "SELECT * FROM pending_reviews WHERE workspace_id=? AND status='pending' "
            "ORDER BY created_at DESC",
            (workspace_id,),
        ).fetchall()
        return [row_to_review(r) for r in rows]

    def update_status(self, review_id: str, status: str, action: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE pending_reviews SET status=?, review_action=?, reviewed_at=? WHERE id=?",
            (status, action, ser(now_utc()), review_id),
        )
        self.conn.commit()

    def expire_old(self) -> int:
        """Mark pending items past expires_at as expired (Doc 04 §10)."""
        cur = self.conn.execute(
            "UPDATE pending_reviews SET status='expired' "
            "WHERE status='pending' AND expires_at < ?",
            (ser(now_utc()),),
        )
        self.conn.commit()
        return cur.rowcount
