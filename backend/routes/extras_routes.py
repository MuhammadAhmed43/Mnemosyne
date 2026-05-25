"""Plan 12 endpoints: snapshot, graph diff, merge, NL query, threads, feedback."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, Request, Response

from backend.security.auth import verify_token
from backend.utils.time import now_utc

router = APIRouter(prefix="/api/v1", tags=["extras"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/snapshot")
async def snapshot(workspace_id: str, request: Request) -> Response:
    md = request.app.state.container.snapshot_service(workspace_id).export_markdown(workspace_id)
    return Response(md, media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename={workspace_id}_snapshot.md"})


def _parse_since(s: str | None) -> datetime:
    if not s:
        return now_utc() - timedelta(days=7)
    # A '+' in the ISO offset can arrive decoded as a space from a query string.
    for cand in (s, s.replace(" ", "+")):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return now_utc() - timedelta(days=7)


@router.get("/workspaces/{workspace_id}/diff")
async def graph_diff(workspace_id: str, request: Request, since: str | None = None) -> dict:
    return request.app.state.container.graph_diff_service(workspace_id).get_diff(workspace_id, _parse_since(since))


@router.post("/workspaces/merge")
async def merge(request: Request, source_id: str = Body(...), target_id: str = Body(...),
                preview: bool = Body(default=False)) -> dict:
    svc = request.app.state.container.merge_service
    return svc.preview(source_id, target_id) if preview else svc.execute(source_id, target_id)


@router.post("/workspaces/{workspace_id}/query")
async def nl_query(workspace_id: str, request: Request, question: str = Body(..., embed=True)) -> dict:
    nodes = request.app.state.container.nl_query_service(workspace_id).query(workspace_id, question)
    return {"results": [n.model_dump(mode="json") for n in nodes], "total": len(nodes)}


@router.get("/workspaces/{workspace_id}/threads")
async def list_threads(workspace_id: str, request: Request) -> dict:
    threads = request.app.state.container.thread_repo(workspace_id).list_threads(workspace_id)
    return {"threads": [t.model_dump(mode="json") for t in threads]}


@router.get("/workspaces/{workspace_id}/threads/{thread_id}")
async def thread_detail(workspace_id: str, thread_id: str, request: Request) -> dict:
    return {"nodes": request.app.state.container.thread_repo(workspace_id).get_thread_nodes(thread_id)}


@router.get("/workspaces/{workspace_id}/feedback/thresholds")
async def feedback_thresholds(workspace_id: str, request: Request) -> dict:
    return request.app.state.container.feedback_service(workspace_id).adjusted_thresholds()
