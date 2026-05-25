from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import EdgeType
from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class MemoryEdge(BaseModel):
    id: str = Field(default_factory=lambda: generate_id("edge"))
    workspace_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    label: str = ""
    weight: float = 1.0
    metadata: dict = Field(default_factory=dict)
    is_active: bool = True
    valid_from: datetime = Field(default_factory=now_utc)
    valid_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now_utc)
