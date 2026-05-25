"""Workspace export/import (Doc 08 §5, UC-09)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["export"], dependencies=[Depends(verify_token)])


@router.get("/workspaces/{workspace_id}/export")
async def export_workspace(workspace_id: str, request: Request) -> dict:
    return request.app.state.container.workspace_service.export_json(workspace_id)


@router.post("/workspaces/import")
async def import_workspace(request: Request, data: dict = Body(...)) -> dict:
    ws = request.app.state.container.workspace_service.import_json(data)
    return {"imported": True, "workspace_id": ws.id, "name": ws.name}
