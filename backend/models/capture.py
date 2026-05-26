from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import CaptureStatus, Platform
from backend.utils.ids import generate_id

MAX_MESSAGE_CHARS = 50_000  # Doc 08 §3 — 413 if exceeded


class CaptureRequest(BaseModel):
    session_id: str
    platform: Platform
    user_message: str
    ai_response: str
    timestamp: datetime
    tab_url: str
    workspace_id: Optional[str] = None  # auto-detect if None
    metadata: dict = Field(default_factory=dict)


class CaptureResult(BaseModel):
    capture_id: str
    status: CaptureStatus
    workspace_id: Optional[str] = None
    estimated_processing_ms: int = 0
    sensitive_data_detected: bool = False
    reason: Optional[str] = None
    workspace_created: bool = False  # a new workspace was auto-created for this turn
    workspace_name: Optional[str] = None  # its name, for user feedback


class CaptureRecord(BaseModel):
    """Internal record persisted to the disk-backed queue journal."""

    id: str = Field(default_factory=lambda: generate_id("cap"))
    session_id: str
    platform: Platform
    user_message: str
    ai_response: str
    workspace_id: str  # provisional routing; the worker may re-route via the LLM
    tab_url: str = ""
    workspace_autocreated: bool = False  # ingest created this ws as a fallback
    status: CaptureStatus = CaptureStatus.QUEUED
    timestamp: datetime
    retry_count: int = 0
    metadata: dict = Field(default_factory=dict)
