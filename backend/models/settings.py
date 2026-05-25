from __future__ import annotations

from pydantic import BaseModel, Field

from backend.models.enums import Platform


class UserSettings(BaseModel):
    capture_enabled: bool = True
    token_budget: int = 2000
    auto_commit_threshold: float = Field(default=0.80, ge=0.0, le=1.0)  # Doc 14 §3
    min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    decay_enabled: bool = True
    decay_schedule_hours: int = 6
    pending_review_expiry_days: int = 7
    sensitive_data_filter: bool = True
    llm_extraction_enabled: bool = True
    cloud_fallback_enabled: bool = False
    embedding_model: str = "bge-m3"
    platforms_enabled: list[Platform] = Field(
        default_factory=lambda: [Platform.CLAUDE, Platform.CHATGPT, Platform.GEMINI]
    )
    custom_blocked_terms: list[str] = Field(default_factory=list)
    show_blocked_notifications: bool = True
    theme: str = "dark"
    sidebar_position: str = "right"
