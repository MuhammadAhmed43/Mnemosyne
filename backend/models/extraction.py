from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.conflict import ConflictCandidate
from backend.models.enums import NodeType
from backend.models.memory_node import MemoryNode
from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class ExtractionCandidate(BaseModel):
    node_type: NodeType
    content: str
    structured_data: dict = Field(default_factory=dict)
    confidence: float
    source_pass: str  # "rule_based" | "ner" | "llm" | merged "rule_based+ner"
    evidence: str = ""
    corroborated_by: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    capture_id: str
    # Pipeline output: candidates routed by confidence. The service layer commits
    # `to_commit` -> MemoryNodes (populating `auto_committed`) after conflict checks.
    to_commit: list[ExtractionCandidate] = Field(default_factory=list)
    pending_review: list[ExtractionCandidate] = Field(default_factory=list)
    discarded: list[ExtractionCandidate] = Field(default_factory=list)
    # Filled by the service after committing:
    auto_committed: list[MemoryNode] = Field(default_factory=list)
    conflicts_detected: list[ConflictCandidate] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None
    duration_ms: int = 0


class SensitivityCheckResult(BaseModel):
    is_sensitive: bool
    pattern_matched: Optional[str] = None  # label only — NEVER the matched text


class PendingReview(BaseModel):
    """A low-confidence extraction awaiting user approval (Doc 07 §2.5)."""

    id: str = Field(default_factory=lambda: generate_id("pend"))
    workspace_id: str
    candidate_type: str
    candidate_content: str
    candidate_data: dict = Field(default_factory=dict)
    candidate_confidence: float = 0.0
    source_session_id: Optional[str] = None
    source_platform: Optional[str] = None
    source_context: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
    expires_at: datetime
    status: str = "pending"  # pending | approved | rejected | expired
    reviewed_at: Optional[datetime] = None
    review_action: Optional[str] = None
