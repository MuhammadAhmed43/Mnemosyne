"""Context reconstruction endpoint (Doc 08 §4)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from backend.models.context import ContextResult
from backend.models.enums import Platform
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["context"], dependencies=[Depends(verify_token)])


@router.get("/context", response_model=ContextResult)
async def get_context(
    request: Request,
    workspace_id: Optional[str] = None,
    hint: Optional[str] = None,
    tab_url: Optional[str] = None,
    platform: Platform = Platform.CLAUDE,
    token_budget: int = Query(default=2000, le=4000),
) -> ContextResult:
    c = request.app.state.container
    ws = workspace_id
    if not ws:
        # Pass tab_url so a saved URL->workspace mapping (platform_mappings) wins
        # deterministically before we fall back to embedding inference / recency.
        ws, _score = c.workspace_service.infer_workspace(hint or "", "", tab_url or "")
    if not ws:
        # No explicit workspace and nothing to infer from (e.g. a fresh chat with
        # no first message yet) -> fall back to the most-recently-active workspace,
        # so the context bar still appears. Mirrors the capture routing fallback.
        active = c.workspace_service.list(status="active")
        ws = active[0].id if active else ""
    if not ws:
        return ContextResult(workspace_id="", workspace_name="", context_string="")
    return c.retrieval_service(ws).get_context(ws, hint, platform.value, token_budget)
