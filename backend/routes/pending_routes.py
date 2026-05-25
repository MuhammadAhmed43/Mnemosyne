"""Pending-review approve/reject (Doc 08 §8)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Request

from backend.errors import NOT_FOUND, MnemosyneError
from backend.models.enums import NodeType, Platform
from backend.models.extraction import ExtractionCandidate
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["pending"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/pending")
async def list_pending(workspace_id: str, request: Request) -> dict:
    items = request.app.state.container.pending_repo(workspace_id).get_pending(workspace_id)
    return {"items": [i.model_dump(mode="json") for i in items], "total": len(items)}


@router.post("/workspaces/{workspace_id}/pending/reject-all")
async def reject_all(workspace_id: str, request: Request, reason: str = Body(default="bulk_rejected", embed=True)) -> dict:
    """Reject every pending item at once (e.g. to clear a low-quality backlog).
    Records negative feedback for each so extraction learns from the rejections."""
    c = request.app.state.container
    repo = c.pending_repo(workspace_id)
    items = repo.get_pending(workspace_id)
    for item in items:
        repo.update_status(item.id, "rejected", reason)
        c.feedback_service(workspace_id).record(None, "rejected", item.candidate_type, item.candidate_confidence)
    return {"rejected": len(items)}


@router.post("/workspaces/{workspace_id}/pending/{review_id}/approve")
async def approve(workspace_id: str, review_id: str, request: Request, edits: Optional[dict] = Body(default=None)) -> dict:
    c = request.app.state.container
    repo = c.pending_repo(workspace_id)
    item = repo.get(review_id)
    if item is None:
        raise MnemosyneError(NOT_FOUND, "Pending item not found", {"review_id": review_id})
    content = (edits or {}).get("content", item.candidate_content)
    data = (edits or {}).get("structured_data", item.candidate_data)
    node = c.graph_service(workspace_id).commit_node(
        workspace_id,
        ExtractionCandidate(node_type=NodeType(item.candidate_type), content=content,
                            structured_data=data, confidence=item.candidate_confidence,
                            source_pass="user_approved", evidence="approved from pending"),
        platform=Platform(item.source_platform) if item.source_platform else Platform.MANUAL,
    )
    c.node_repo(workspace_id).update_fields(node.id, user_verified=True)
    repo.update_status(review_id, "approved", "approved")
    action = "edited" if edits else "approved"
    c.feedback_service(workspace_id).record(node.id, action, item.candidate_type, item.candidate_confidence)
    return {"approved": True, "node_id": node.id}


@router.post("/workspaces/{workspace_id}/pending/{review_id}/reject")
async def reject(workspace_id: str, review_id: str, request: Request, reason: str = Body(default="inaccurate", embed=True)) -> dict:
    c = request.app.state.container
    item = c.pending_repo(workspace_id).get(review_id)
    c.pending_repo(workspace_id).update_status(review_id, "rejected", reason)
    if item:
        c.feedback_service(workspace_id).record(None, "rejected", item.candidate_type, item.candidate_confidence)
    return {"rejected": True}
