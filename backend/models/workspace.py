from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import WorkspaceStatus
from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class Workspace(BaseModel):
    id: str = Field(default_factory=lambda: generate_id("ws"))
    name: str
    description: str = ""
    color: str = "#6366F1"
    icon: str = "🧠"
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    capture_enabled: bool = True
    tags: list[str] = Field(default_factory=list)

    # Denormalized stats
    entity_count: int = 0
    node_count: int = 0
    memory_health_score: float = 1.0

    # Workspace auto-detection (Doc 10 §8)
    summary_embedding_id: Optional[str] = None
    summary_text: Optional[str] = None
    embedding_model: str = "bge-m3"

    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    last_active: datetime = Field(default_factory=now_utc)
    settings: dict = Field(default_factory=dict)
