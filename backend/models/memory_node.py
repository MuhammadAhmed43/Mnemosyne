from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import MemoryTier, NodeStatus, NodeType, Platform
from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class MemoryNode(BaseModel):
    id: str = Field(default_factory=lambda: generate_id("node"))
    workspace_id: str
    node_type: NodeType
    tier: MemoryTier = MemoryTier.EPISODIC

    content: str
    structured_data: dict = Field(default_factory=dict)

    # Provenance
    source_session_id: Optional[str] = None
    source_platform: Platform = Platform.MANUAL
    extraction_confidence: float = 1.0
    extracted_at: Optional[datetime] = None
    user_verified: bool = False

    # Importance & decay
    importance_score: float = 0.7
    decay_rate: float = 0.05
    is_permanent: bool = False
    reinforcement_count: int = 0

    # Status & temporal versioning
    status: NodeStatus = NodeStatus.ACTIVE
    version: int = 1
    valid_from: datetime = Field(default_factory=now_utc)
    valid_until: Optional[datetime] = None  # None = current version

    embedding_id: Optional[str] = None  # Qdrant point ID

    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    last_accessed: datetime = Field(default_factory=now_utc)
    changed_by: str = "system"

    # Conflict tracking (Doc 04 §2.1)
    conflicts_with: list[str] = Field(default_factory=list)
    resolved_by: Optional[str] = None


class NodeVersion(BaseModel):
    """Immutable historical snapshot of a node (Doc 07 §2.3)."""

    id: str = Field(default_factory=lambda: generate_id("ver"))
    node_id: str
    workspace_id: str
    version: int
    content: str
    structured_data: dict = Field(default_factory=dict)
    importance_score: Optional[float] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    changed_by: str = "system"
    change_reason: Optional[str] = None
    archived_at: datetime = Field(default_factory=now_utc)
