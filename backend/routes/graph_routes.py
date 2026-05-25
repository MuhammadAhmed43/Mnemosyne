"""Graph visualization data + search (Doc 08 §7, UC-21 global search)."""

from __future__ import annotations


from fastapi import APIRouter, Depends, Query, Request

from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["graph"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/graph")
async def get_graph(workspace_id: str, request: Request, max_nodes: int = Query(default=200, le=1000)) -> dict:
    data = request.app.state.container.graph_service(workspace_id).get_graph_data(workspace_id)
    nodes = data["nodes"][:max_nodes]
    node_ids = {n.id for n in nodes}
    return {
        "nodes": [
            {"id": n.id, "label": n.content[:40], "type": n.node_type.value, "importance": n.importance_score}
            for n in nodes
        ],
        "edges": [
            {"id": e.id, "source": e.source_node_id, "target": e.target_node_id, "type": e.edge_type.value, "label": e.label}
            for e in data["edges"]
            if e.source_node_id in node_ids and e.target_node_id in node_ids
        ],
        "node_count": len(nodes),
        "edge_count": len(data["edges"]),
    }


@router.get("/workspaces/{workspace_id}/search")
async def search(workspace_id: str, request: Request, q: str) -> dict:
    nodes = request.app.state.container.node_repo(workspace_id).search_fts(workspace_id, q)
    return {"results": [n.model_dump(mode="json") for n in nodes], "total": len(nodes)}


@router.get("/search/global")
async def global_search(request: Request, q: str) -> dict:
    c = request.app.state.container
    grouped = {}
    for ws in c.workspace_repo.get_active():
        hits = c.node_repo(ws.id).search_fts(ws.id, q)
        if hits:
            grouped[ws.name] = [n.model_dump(mode="json") for n in hits]
    return {"results_by_workspace": grouped}
