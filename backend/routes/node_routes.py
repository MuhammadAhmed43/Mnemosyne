"""Memory node CRUD + boost + manual add (Doc 08 §6)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from backend.errors import NOT_FOUND, MnemosyneError
from backend.models.enums import NodeType, Platform
from backend.models.extraction import ExtractionCandidate
from backend.models.memory_node import MemoryNode
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["nodes"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/nodes")
async def list_nodes(
    workspace_id: str,
    request: Request,
    type: Optional[str] = Query(default="all"),
    status: str = Query(default="active"),
    sort: str = Query(default="importance"),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = None,
) -> dict:
    repo = request.app.state.container.node_repo(workspace_id)
    if search:
        nodes = repo.search_fts(workspace_id, search, limit=limit)
        total = len(nodes)
    else:
        nodes, total = repo.list_nodes(workspace_id, type, status, sort, limit, offset)
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/workspaces/{workspace_id}/node-counts")
async def node_counts(workspace_id: str, request: Request, search: Optional[str] = None) -> dict:
    """Per-type active counts for the dashboard chip row. Honors an optional
    search so the chips track the search results. Distinct path (`node-counts`,
    not `nodes/...`) so it can't be mistaken for a node id."""
    repo = request.app.state.container.node_repo(workspace_id)
    counts = repo.count_by_type_search(workspace_id, search) if search else repo.count_by_type(workspace_id)
    return {"counts": counts, "total": sum(counts.values())}


@router.get("/workspaces/{workspace_id}/nodes/{node_id}")
async def get_node(workspace_id: str, node_id: str, request: Request) -> dict:
    c = request.app.state.container
    repo = c.node_repo(workspace_id)
    node = repo.get(node_id)
    if node is None:
        raise MnemosyneError(NOT_FOUND, "Node not found", {"node_id": node_id})
    versions = repo.get_version_history(node_id)
    edges = c.edge_repo(workspace_id).get_edges_for_node(node_id)
    return {
        "node": node.model_dump(mode="json"),
        "version_history": [v.model_dump(mode="json") for v in versions],
        "connected_edges": [e.model_dump(mode="json") for e in edges],
    }


@router.put("/workspaces/{workspace_id}/nodes/{node_id}")
async def update_node(
    workspace_id: str,
    node_id: str,
    request: Request,
    content: Optional[str] = Body(default=None),
    structured_data: Optional[dict] = Body(default=None),
    importance_score: Optional[float] = Body(default=None),
    is_permanent: Optional[bool] = Body(default=None),
) -> dict:
    c = request.app.state.container
    graph = c.graph_service(workspace_id)
    if content is not None:
        updated = graph.update_node_content(node_id, workspace_id, content, structured_data, changed_by="user")
        if updated is None:
            raise MnemosyneError(NOT_FOUND, "Node not found", {"node_id": node_id})
    if importance_score is not None or is_permanent is not None:
        fields = {"user_verified": True}
        if importance_score is not None:
            fields["importance_score"] = importance_score
        if is_permanent is not None:
            fields["is_permanent"] = is_permanent
        c.node_repo(workspace_id).update_fields(node_id, **fields)
    return {"updated": True}


@router.post("/workspaces/{workspace_id}/nodes/{node_id}/boost")
async def boost_node(
    workspace_id: str,
    node_id: str,
    request: Request,
    boost_amount: float = Body(..., ge=0.0, le=1.0),
    reason: str = Body(default="user_explicit"),
) -> dict:
    c = request.app.state.container
    node = c.node_repo(workspace_id).get(node_id)
    if node is None:
        raise MnemosyneError(NOT_FOUND, "Node not found", {"node_id": node_id})
    c.graph_service(workspace_id).boost_node(
        node_id, workspace_id, min(1.0, node.importance_score + boost_amount)
    )
    return {"boosted": True, "importance_score": min(1.0, node.importance_score + boost_amount)}


@router.post("/workspaces/{workspace_id}/nodes/{node_id}/move")
async def move_node(
    workspace_id: str,
    node_id: str,
    request: Request,
    target_workspace_id: str = Body(..., embed=True),
) -> dict:
    """Move a node to another workspace. Each workspace is a separate (encrypted)
    DB + vector collection, so this re-creates the node in the target (re-embedded,
    re-linked) preserving its verification/importance, then removes it from the
    source. Used when auto-routing filed a memory in the wrong place."""
    c = request.app.state.container
    if workspace_id == target_workspace_id:
        return {"moved": False, "reason": "same workspace"}
    node = c.node_repo(workspace_id).get(node_id)
    if node is None:
        raise MnemosyneError(NOT_FOUND, "Node not found", {"node_id": node_id})
    if c.workspace_service.get(target_workspace_id) is None:
        raise MnemosyneError(NOT_FOUND, "Target workspace not found", {"workspace_id": target_workspace_id})

    new_node = c.graph_service(target_workspace_id).commit_node(
        target_workspace_id,
        ExtractionCandidate(node_type=node.node_type, content=node.content,
                            structured_data=node.structured_data, confidence=node.extraction_confidence,
                            source_pass="moved", evidence=f"moved from {workspace_id}"),
        platform=node.source_platform,
    )
    c.node_repo(target_workspace_id).update_fields(
        new_node.id, user_verified=node.user_verified,
        importance_score=node.importance_score, is_permanent=node.is_permanent,
    )
    c.graph_service(workspace_id).hard_delete_node(node_id, workspace_id)
    return {"moved": True, "new_node_id": new_node.id, "target_workspace_id": target_workspace_id}


@router.delete("/workspaces/{workspace_id}/nodes/{node_id}")
async def delete_node(workspace_id: str, node_id: str, request: Request, hard: bool = Query(default=False)) -> dict:
    graph = request.app.state.container.graph_service(workspace_id)
    if hard:
        graph.hard_delete_node(node_id, workspace_id)
    else:
        graph.archive_node(node_id, workspace_id, reason="user_delete")
    return {"deleted": True, "hard": hard}


@router.post("/workspaces/{workspace_id}/nodes/manual", response_model=MemoryNode)
async def create_manual_node(
    workspace_id: str,
    request: Request,
    node_type: NodeType = Body(...),
    content: str = Body(...),
    structured_data: dict = Body(default_factory=dict),
) -> MemoryNode:
    graph = request.app.state.container.graph_service(workspace_id)
    node = graph.commit_node(
        workspace_id,
        ExtractionCandidate(node_type=node_type, content=content, structured_data=structured_data,
                            confidence=1.0, source_pass="manual", evidence="manual"),
        platform=Platform.MANUAL,
    )
    graph.nodes.update_fields(node.id, user_verified=True)
    return node


@router.post("/notes")
async def create_note(
    request: Request,
    text: str = Body(...),
    platform: Platform = Body(default=Platform.MANUAL),
    tab_url: str = Body(default=""),
    workspace_id: Optional[str] = Body(default=None),
) -> dict:
    """Save a free-text note (e.g. right-click 'Save selection') as a verified
    USER_NOTE. Resolves the target workspace the same way context does: explicit
    -> URL/embedding inference -> most-recently-active fallback, so the user never
    has to pick one for a quick save."""
    text = (text or "").strip()
    if not text:
        raise MnemosyneError(NOT_FOUND, "Empty note")
    c = request.app.state.container
    ws = workspace_id
    if not ws:
        ws, _ = c.workspace_service.infer_workspace("", "", tab_url or "")
    if not ws:
        active = c.workspace_service.list(status="active")
        ws = active[0].id if active else ""
    if not ws:
        raise MnemosyneError(NOT_FOUND, "No workspace available to save into")
    graph = c.graph_service(ws)
    node = graph.commit_node(
        ws,
        ExtractionCandidate(node_type=NodeType.USER_NOTE, content=text, structured_data={"source": "manual_selection"},
                            confidence=1.0, source_pass="manual", evidence="user_selection"),
        platform=platform,
    )
    graph.nodes.update_fields(node.id, user_verified=True)
    return {"saved": True, "workspace_id": ws, "node_id": node.id}
