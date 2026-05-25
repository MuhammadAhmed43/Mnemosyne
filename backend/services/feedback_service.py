"""Extraction feedback loop — tune thresholds from user corrections (Plan 12 §5)."""

from __future__ import annotations

from typing import Optional

from backend.repositories.feedback_repo import FeedbackRepository


class FeedbackService:
    def __init__(self, feedback_repo: FeedbackRepository):
        self.repo = feedback_repo

    def record(
        self,
        node_id: Optional[str],
        action: str,  # approved | edited | rejected
        original_type: Optional[str],
        original_confidence: Optional[float] = None,
        corrected_type: Optional[str] = None,
    ) -> None:
        self.repo.insert(node_id, action, original_type, original_confidence, corrected_type)

    def adjusted_thresholds(self) -> dict[str, float]:
        """Suggest per-type auto-commit thresholds from rejection/edit rates."""
        out: dict[str, float] = {}
        for node_type, data in self.repo.get_stats().items():
            total = max(data["total"], 1)
            rejection = data["rejected"] / total
            edit = data["edited"] / total
            if rejection > 0.20:
                out[node_type] = round(min(0.95, 0.80 + rejection * 0.3), 3)
            elif edit > 0.30:
                out[node_type] = round(min(0.90, 0.80 + edit * 0.2), 3)
        return out
