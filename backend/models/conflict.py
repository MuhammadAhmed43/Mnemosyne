from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import ConflictStrategy, ConflictType, ResolutionStatus
from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class ConflictCandidate(BaseModel):
    id: str = Field(default_factory=lambda: generate_id("conf"))
    workspace_id: str
    node_a_id: str
    node_b_id: str
    conflict_type: ConflictType
    similarity_score: float = 0.0
    contradiction_score: float = 0.0
    suggested_strategy: ConflictStrategy
    auto_resolvable: bool = False
    status: ResolutionStatus = ResolutionStatus.PENDING
    detected_at: datetime = Field(default_factory=now_utc)


class ResolutionEvent(BaseModel):
    id: str = Field(default_factory=lambda: generate_id("res"))
    workspace_id: str
    conflict_id: str
    conflict_type: ConflictType
    strategy_used: ConflictStrategy
    status: ResolutionStatus
    winning_node_id: Optional[str] = None
    archived_node_ids: list[str] = Field(default_factory=list)
    custom_resolution: Optional[str] = None
    evidence: str = ""
    confidence: float = 1.0
    resolved_by: str = "system"  # "system" or user id
    resolved_at: datetime = Field(default_factory=now_utc)
