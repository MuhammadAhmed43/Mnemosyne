"""Workspace CRUD (Doc 08 §5)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from backend.errors import NOT_FOUND, WORKSPACE_FULL, MnemosyneError
from backend.models.extraction import ExtractionCandidate
from backend.models.workspace import Workspace
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["workspaces"], dependencies=[Depends(verify_token)])


@router.get("/workspaces")
async def list_workspaces(
    request: Request,
    status: Optional[str] = Query(default="active"),
    sort: str = Query(default="last_active"),
) -> dict:
    c = request.app.state.container
    wss = c.workspace_service.list(status, sort)
    # Refresh node_count from the live store. The stored field is only updated on
    # a health check, so it goes stale (shows 0) and makes populated workspaces
    # look empty in the popup/dashboard. Counting active nodes is cheap.
    out = []
    for w in wss:
        try:
            w.node_count = c.node_repo(w.id).count(w.id)
        except Exception:  # noqa: BLE001 — a missing/locked ws shouldn't break the list
            pass
        out.append(w.model_dump(mode="json"))
    return {"workspaces": out, "total": len(wss)}


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


def _move_all_nodes(c, src: str, dst: str) -> int:
    """Re-home every active node from src workspace into dst (re-embedded, deduped
    by commit_node), preserving verification/importance. Returns count moved."""
    moved = 0
    for node in c.node_repo(src).get_active(src, limit=10000):
        new_node = c.graph_service(dst).commit_node(
            dst,
            ExtractionCandidate(
                node_type=node.node_type, content=node.content,
                structured_data=node.structured_data, confidence=node.extraction_confidence,
                source_pass="merged", evidence=f"merged from {src}",
            ),
            platform=node.source_platform,
        )
        c.node_repo(dst).update_fields(
            new_node.id, user_verified=node.user_verified,
            importance_score=node.importance_score, is_permanent=node.is_permanent,
        )
        moved += 1
    return moved


@router.post("/workspaces/cleanup")
async def cleanup_workspaces(
    request: Request,
    merge_duplicates: bool = Body(default=True),
    delete_empty: bool = Body(default=True),
) -> dict:
    """Tidy up the artifacts of earlier routing bugs: merge same-named duplicate
    workspaces (keep the one with the most memories, move the rest in) and delete
    workspaces that have no memories. Returns a report of exactly what changed."""
    c = request.app.state.container
    report: dict = {"merged": [], "deleted_empty": []}
    active = c.workspace_service.list(status="active")
    counts = {w.id: c.node_repo(w.id).count(w.id) for w in active}

    if merge_duplicates:
        groups: dict[str, list] = {}
        for w in active:
            groups.setdefault(w.name.strip().lower(), []).append(w)
        for group in groups.values():
            if len(group) < 2:
                continue
            canonical = max(group, key=lambda w: counts.get(w.id, 0))
            for w in group:
                if w.id == canonical.id:
                    continue
                moved = _move_all_nodes(c, w.id, canonical.id)
                c.workspace_service.delete(w.id)
                report["merged"].append({"from": w.name, "into_id": canonical.id, "moved": moved})
        active = c.workspace_service.list(status="active")
        counts = {w.id: c.node_repo(w.id).count(w.id) for w in active}

    if delete_empty:
        for w in active:
            if counts.get(w.id, 0) == 0:
                c.workspace_service.delete(w.id)
                report["deleted_empty"].append(w.name)

    return report


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
