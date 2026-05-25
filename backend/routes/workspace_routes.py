"""Workspace CRUD (Doc 08 §5)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from backend.errors import NOT_FOUND, WORKSPACE_FULL, MnemosyneError
from backend.models.workspace import Workspace
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["workspaces"], dependencies=[Depends(verify_token)])


@router.get("/workspaces")
async def list_workspaces(
    request: Request,
    status: Optional[str] = Query(default="active"),
    sort: str = Query(default="last_active"),
) -> dict:
    wss = request.app.state.container.workspace_service.list(status, sort)
    return {"workspaces": [w.model_dump(mode="json") for w in wss], "total": len(wss)}


@router.post("/workspaces", status_code=201, response_model=Workspace)
async def create_workspace(
    request: Request,
    name: str = Body(...),
    description: str = Body(default=""),
    tags: list[str] = Body(default_factory=list),
    color: str = Body(default="#6366F1"),
    icon: str = Body(default="🧠"),
) -> Workspace:
    try:
        return request.app.state.container.workspace_service.create(name, description, tags, color, icon)
    except ValueError as e:
        raise MnemosyneError(WORKSPACE_FULL, str(e)) from e


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str, request: Request) -> Workspace:
    ws = request.app.state.container.workspace_service.get(workspace_id)
    if ws is None:
        raise MnemosyneError(NOT_FOUND, "Workspace not found", {"workspace_id": workspace_id})
    return ws


@router.put("/workspaces/{workspace_id}")
async def update_workspace(workspace_id: str, request: Request, fields: dict = Body(...)) -> dict:
    request.app.state.container.workspace_repo.update_fields(workspace_id, **fields)
    return {"updated": True}


@router.post("/workspaces/{workspace_id}/archive")
async def archive_workspace(workspace_id: str, request: Request) -> dict:
    request.app.state.container.workspace_service.archive(workspace_id)
    return {"archived": True}


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    request: Request,
    confirm: bool = Query(...),
    export_first: bool = Query(default=False),
) -> dict:
    if not confirm:
        raise MnemosyneError(NOT_FOUND, "confirm=true required")
    svc = request.app.state.container.workspace_service
    export = svc.export_json(workspace_id) if export_first else None
    svc.delete(workspace_id)
    return {"deleted": True, "export": export}


@router.get("/workspaces/{workspace_id}/health")
async def workspace_health(workspace_id: str, request: Request) -> dict:
    return {"memory_health_score": request.app.state.container.workspace_service.get_health(workspace_id)}


@router.post("/mappings")
async def create_mapping(
    request: Request,
    platform: str = Body(...),
    workspace_id: str = Body(...),
    tab_url: str = Body(...),
) -> dict:
    """Remember 'this URL -> this workspace' (set when the user picks a workspace
    in the context bar). Used by context inference on the next visit."""
    svc = request.app.state.container.workspace_service
    if svc.get(workspace_id) is None:
        raise MnemosyneError(NOT_FOUND, "Workspace not found", {"workspace_id": workspace_id})
    pattern = svc.remember_mapping(platform, workspace_id, tab_url)
    return {"remembered": True, "url_pattern": pattern}
