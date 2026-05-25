from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.utils.ids import generate_id
from backend.utils.time import now_utc


class ConversationThread(BaseModel):
    """Links nodes extracted from one conversation session (Plan 12 §1)."""

    id: str = Field(default_factory=lambda: generate_id("thread"))
    workspace_id: str
    session_id: str
    platform: str
    started_at: datetime = Field(default_factory=now_utc)
    ended_at: Optional[datetime] = None
    turn_count: int = 0
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
