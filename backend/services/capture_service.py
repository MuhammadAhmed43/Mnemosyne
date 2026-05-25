"""Capture ingestion: sanitize -> resolve workspace -> session -> build record (Doc 10 §2).

Does the synchronous front of capture. Returns (CaptureResult, CaptureRecord|None);
the route/worker layer enqueues the record for the extraction pipeline. Sensitive
data is blocked here before anything is stored (Doc 14 §1).
"""

from __future__ import annotations

from typing import Optional

from backend.db.manager import DatabaseManager
from backend.extraction.sensitive_filter import check_custom_blocked_terms, contains_sensitive_data
from backend.models.capture import CaptureRecord, CaptureRequest, CaptureResult
from backend.models.enums import CaptureStatus
from backend.repositories.session_repo import SessionRepository
from backend.repositories.settings_repo import SettingsRepository
from backend.services.workspace_service import (
    AUTO_CREATE_MAX_SIM,
    NEEDS_NEW_WORKSPACE,
    WorkspaceService,
)

# A topic-switch turn should be substantial enough to justify (and name) a new
# workspace — don't spin one up for "hey" or "thanks".
NEW_WS_MIN_CHARS = 80


class CaptureService:
    def __init__(
        self,
        workspace_service: WorkspaceService,
        db: DatabaseManager,
        settings_repo: SettingsRepository,
    ):
        self.workspaces = workspace_service
        self.db = db
        self.settings = settings_repo

    def ingest(self, req: CaptureRequest) -> tuple[CaptureResult, Optional[CaptureRecord]]:
        combined = f"{req.user_message}\n{req.ai_response}"

        # Gate: sensitive data (before anything is stored)
        sens = contains_sensitive_data(combined)
        if sens.is_sensitive:
            return CaptureResult(
                capture_id="", status=CaptureStatus.BLOCKED,
                sensitive_data_detected=True, reason=sens.pattern_matched,
            ), None

        settings = self.settings.get_user_settings()
        custom = check_custom_blocked_terms(combined, settings.custom_blocked_terms)
        if custom.is_sensitive:
            return CaptureResult(
                capture_id="", status=CaptureStatus.BLOCKED,
                sensitive_data_detected=True, reason=custom.pattern_matched,
            ), None

        # Resolve workspace: explicit -> inferred -> auto-create (on a confident
        # topic mismatch) -> fall back to most-recently-active.
        workspace_id = req.workspace_id
        best_conf = 1.0  # explicit pick is treated as certain
        if not workspace_id:
            workspace_id, best_conf = self.workspaces.infer_workspace(
                req.user_message, req.ai_response, req.tab_url
            )

        created_ws = None
        if workspace_id == NEEDS_NEW_WORKSPACE or not workspace_id:
            active = self.workspaces.list(status="active")  # sorted by last_active desc
            substantive = len(combined.strip()) >= NEW_WS_MIN_CHARS
            can_embed = self.workspaces.embeddings.available
            if not active:
                # Cold start: first conversation -> first workspace (never drop it).
                created_ws = self._safe_create_topic(req)
                workspace_id = created_ws.id if created_ws else ""
            elif can_embed and substantive and best_conf < AUTO_CREATE_MAX_SIM:
                # Confident mismatch against every existing workspace: this is a new
                # topic. Make a workspace named from the message and pin this chat's
                # URL to it so the rest of the conversation stays together.
                created_ws = self._safe_create_topic(req)
                if created_ws:
                    workspace_id = created_ws.id
                    try:
                        self.workspaces.remember_mapping(req.platform.value, workspace_id, req.tab_url)
                    except Exception:  # noqa: BLE001 — mapping is best-effort
                        pass
                else:
                    workspace_id = active[0].id
            else:
                # Ambiguous near-miss, no embeddings, or trivial turn -> don't sprawl.
                workspace_id = active[0].id

        if not workspace_id:
            return CaptureResult(
                capture_id="", status=CaptureStatus.SKIPPED, reason="no_workspace_exists",
            ), None

        sessions = SessionRepository(self.db.get_workspace(workspace_id))
        sessions.upsert(workspace_id, req.session_id, req.platform.value, req.tab_url)
        sessions.increment(req.session_id, turn_count=1, capture_count=1)

        record = CaptureRecord(
            session_id=req.session_id, platform=req.platform,
            user_message=req.user_message, ai_response=req.ai_response,
            workspace_id=workspace_id, timestamp=req.timestamp, metadata=req.metadata,
        )
        return CaptureResult(
            capture_id=record.id, status=CaptureStatus.QUEUED,
            workspace_id=workspace_id, estimated_processing_ms=400,
            workspace_created=created_ws is not None,
            workspace_name=created_ws.name if created_ws else None,
        ), record

    def _safe_create_topic(self, req: CaptureRequest):
        """Create a topic workspace, tolerating the max-workspaces cap (caller
        falls back to the most-recent workspace if this returns None)."""
        try:
            return self.workspaces.create_for_topic(req.user_message, req.ai_response, req.platform.value)
        except Exception:  # noqa: BLE001
            return None
