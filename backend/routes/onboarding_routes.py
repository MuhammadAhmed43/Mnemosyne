"""Onboarding endpoints: quick-add, name suggestion, retrospective, events (Doc 17)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Request

from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"], dependencies=[Depends(verify_token)])


@router.post("/suggest-name")
async def suggest_name(request: Request, description: str = Body(..., embed=True)) -> dict:
    name = request.app.state.container.onboarding_service.suggest_workspace_name(description)
    return {"suggested_name": name}


@router.post("/quick-add")
async def quick_add(
    request: Request,
    workspace_id: str = Body(...),
    goal: Optional[str] = Body(default=None),
    tech_stack: Optional[str] = Body(default=None),
    key_person: Optional[str] = Body(default=None),
) -> dict:
    c = request.app.state.container
    nodes = c.onboarding_service.process_quick_add(
        c.graph_service(workspace_id), workspace_id, goal, tech_stack, key_person
    )
    return {"created_nodes": len(nodes), "node_ids": [n.id for n in nodes]}


@router.post("/retrospective")
async def retrospective(
    request: Request,
    workspace_id: str = Body(...),
    text: str = Body(...),
    platform: str = Body(default="claude"),
) -> dict:
    c = request.app.state.container
    return await c.onboarding_service.retrospective_extraction(
        c.pipeline, c.pending_repo(workspace_id), workspace_id, text, platform
    )


@router.post("/event")
async def log_event(request: Request, event_type: str = Body(...), metadata: dict = Body(default_factory=dict)) -> dict:
    request.app.state.container.onboarding_service.log_event(event_type, metadata)
    return {"ok": True}


@router.get("/nudge")
async def get_nudge() -> dict:
    return {"nudge": None}  # nudge timing logic is a future enhancement
