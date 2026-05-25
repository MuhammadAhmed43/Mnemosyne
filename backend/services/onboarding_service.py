"""Cold-start: quick-add seeding, name suggestion, retrospective import, events (Doc 17)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

from backend.models.capture import CaptureRecord
from backend.models.enums import NodeType, Platform
from backend.models.extraction import ExtractionCandidate, PendingReview
from backend.repositories.onboarding_repo import OnboardingRepository
from backend.utils.time import now_utc

if TYPE_CHECKING:
    from backend.extraction.pipeline import ExtractionPipeline
    from backend.repositories.pending_review_repo import PendingReviewRepository
    from backend.services.graph_service import GraphService

_FILLER = {"a", "an", "the", "my", "our", "for", "of", "on", "in", "to", "and", "with", "building", "working"}
PENDING_TTL_DAYS = 7
_TURN_RE = re.compile(r"(?:^|\n)\s*(?:USER|Human|Me)\s*:\s*(.*?)(?=\n\s*(?:AI|Assistant|Claude|GPT)\s*:)"
                      r"\s*(?:AI|Assistant|Claude|GPT)\s*:\s*(.*?)(?=\n\s*(?:USER|Human|Me)\s*:|\Z)",
                      re.IGNORECASE | re.DOTALL)


class OnboardingService:
    def __init__(self, onboarding_repo: OnboardingRepository):
        self.repo = onboarding_repo

    def log_event(self, event_type: str, metadata: Optional[dict] = None) -> str:
        return self.repo.log_event(event_type, metadata)

    def set_state(self, key: str, value: str) -> None:
        self.repo.set_state(key, value)

    def get_state(self, key: str) -> Optional[str]:
        return self.repo.get_state(key)

    def suggest_workspace_name(self, description: str) -> str:
        """Heuristic name from a free-text description (LLM enhancement is a future hook)."""
        words = [w for w in re.findall(r"[A-Za-z0-9.+\-]+", description) if w.lower() not in _FILLER]
        name = " ".join(w.capitalize() if w.islower() else w for w in words[:4])
        return name or "My Workspace"

    def process_quick_add(
        self, graph: "GraphService", workspace_id: str,
        goal: Optional[str] = None, tech_stack: Optional[str] = None, key_person: Optional[str] = None,
    ) -> list:
        specs = [
            (goal, NodeType.GOAL, {"status": "ACTIVE"}),
            (tech_stack, NodeType.TECHNICAL_FACT, {"entity": "stack", "value": tech_stack}),
            (key_person, NodeType.ENTITY, {"entity_type": "person"}),
        ]
        created = []
        for content, ntype, data in specs:
            if not content:
                continue
            node = graph.commit_node(
                workspace_id,
                ExtractionCandidate(node_type=ntype, content=content, structured_data=data,
                                    confidence=1.0, source_pass="manual", evidence="quick_add"),
                platform=Platform.MANUAL,
            )
            graph.nodes.update_fields(node.id, user_verified=True)
            created.append(node)
        self.log_event("quick_add_submitted", {"count": len(created)})
        return created

    async def retrospective_extraction(
        self, pipeline: "ExtractionPipeline", pending_repo: "PendingReviewRepository",
        workspace_id: str, raw_text: str, platform: str,
    ) -> dict:
        """All retrospective extractions go to pending review, never auto-commit (Doc 17 §12)."""
        turns = _TURN_RE.findall(raw_text) or [(raw_text, "")]
        candidates: list[ExtractionCandidate] = []
        for user_msg, ai_msg in turns:
            rec = CaptureRecord(
                session_id=f"retro_{now_utc().timestamp()}", platform=Platform(platform),
                user_message=user_msg.strip(), ai_response=ai_msg.strip(),
                workspace_id=workspace_id, timestamp=now_utc(),
            )
            result = await pipeline.run(rec)
            candidates.extend(result.to_commit + result.pending_review)  # force all -> pending

        expires = now_utc() + timedelta(days=PENDING_TTL_DAYS)
        for c in candidates:
            pending_repo.create(PendingReview(
                workspace_id=workspace_id, candidate_type=c.node_type.value,
                candidate_content=c.content, candidate_data=c.structured_data,
                candidate_confidence=c.confidence, source_platform=platform,
                source_context="retrospective import", expires_at=expires,
            ))
        return {"turns_processed": len(turns), "candidates_total": len(candidates), "all_pending_review": True}
