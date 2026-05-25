"""Conflict listing, resolution, and metrics (Doc 08 §9, Doc 05 §8)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Request

from backend.errors import NOT_FOUND, MnemosyneError
from backend.models.enums import ResolutionStatus
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["conflicts"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/conflicts")
async def list_conflicts(workspace_id: str, request: Request, status: Optional[str] = None) -> dict:
    repo = request.app.state.container.conflict_repo(workspace_id)
    items = repo.get_pending(workspace_id) if status == "pending" else repo.get_all(workspace_id)
    return {"conflicts": [c.model_dump(mode="json") for c in items], "total": len(items)}


@router.post("/workspaces/{workspace_id}/conflicts/{conflict_id}/resolve")
async def resolve(
    workspace_id: str,
    conflict_id: str,
    request: Request,
    strategy: str = Body(...),  # keep_a | keep_b | merge | custom
    merged_content: Optional[str] = Body(default=None),
    reason: str = Body(default=""),
) -> dict:
    c = request.app.state.container
    repo = c.conflict_repo(workspace_id)
    conflict = repo.get(conflict_id)
    if conflict is None:
        raise MnemosyneError(NOT_FOUND, "Conflict not found", {"conflict_id": conflict_id})
    winner = None
    if strategy == "keep_a":
        winner = conflict.node_a_id
    elif strategy == "keep_b":
        winner = conflict.node_b_id
    event = c.conflict_service(workspace_id).user_resolve(conflict, winner, merged_content, reason)
    repo.resolve(conflict_id, event)
    return {"resolved": True, "winning_node_id": winner}


@router.get("/workspaces/{workspace_id}/conflicts/metrics")
async def metrics(workspace_id: str, request: Request) -> dict:
    allc = request.app.state.container.conflict_repo(workspace_id).get_all(workspace_id)
    resolved = [c for c in allc if c.status != ResolutionStatus.PENDING]
    pending = [c for c in allc if c.status == ResolutionStatus.PENDING]
    auto = [c for c in resolved if c.status == ResolutionStatus.AUTO_RESOLVED]
    dismissed = [c for c in resolved if c.status == ResolutionStatus.DISMISSED]
    return {
        "auto_resolve_rate": round(len(auto) / max(len(resolved), 1) * 100, 1),
        "queue_depth": len(pending),
        "false_positive_rate": round(len(dismissed) / max(len(resolved), 1) * 100, 1),
        "total": len(allc),
    }
