"""Health check (Doc 08 §11). Unauthenticated so the extension can detect the
engine during onboarding before a token is configured."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from backend.models.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/pair")
async def pair(request: Request) -> dict:
    """Hand the auth token to the extension during the first-run pairing window.

    Unauthenticated by necessity (the extension has no token yet). CORS restricts
    browser callers to the extension origin; the short window bounds exposure to
    other local processes (Doc 13 treats local malware as out-of-scope for v1).
    """
    app = request.app
    elapsed = time.monotonic() - app.state.start_time
    if elapsed > app.state.container.config.pairing_window_seconds:
        raise HTTPException(status_code=403, detail="Pairing window closed; restart engine to re-pair")
    return {"token": app.state.container.config.auth_token}


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    c = request.app.state.container
    total_nodes = 0
    for ws in c.workspace_repo.get_active():
        total_nodes += c.node_repo(ws.id).count(ws.id)
    return HealthResponse(
        status="healthy",
        version=c.config.version,
        uptime_seconds=int(time.monotonic() - request.app.state.start_time),
        database_ok=True,
        vector_store_ok=c.embedding.available,
        ollama_available=await c.pipeline.llm.is_available(),
        queue_depth=request.app.state.queue.qsize(),
        workspace_count=c.workspace_repo.count_active(),
        total_node_count=total_nodes,
        encryption_at_rest=c.db.encryption_active,
    )
