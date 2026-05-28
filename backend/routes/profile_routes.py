"""About-me (global profile) memory: who the user is / how they work.
Injected into every chat alongside the active workspace's brief."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from backend.errors import INVALID_REQUEST, MnemosyneError
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["profile"], dependencies=[Depends(verify_token)])


@router.get("/profile")
async def list_profile(request: Request) -> dict:
    repo = request.app.state.container.profile_repo()
    return {"items": repo.list()}


@router.post("/profile")
async def add_profile(request: Request, content: str = Body(..., embed=True),
                      kind: str = Body(default="fact")) -> dict:
    text = (content or "").strip()
    if not text:
        raise MnemosyneError(INVALID_REQUEST, "content is required")
    return request.app.state.container.profile_repo().add(text, kind=kind, source="user")


@router.put("/profile/{item_id}")
async def update_profile(item_id: str, request: Request, content: str = Body(..., embed=True)) -> dict:
    text = (content or "").strip()
    if not text:
        raise MnemosyneError(INVALID_REQUEST, "content is required")
    request.app.state.container.profile_repo().update(item_id, text)
    return {"updated": True}


@router.delete("/profile/{item_id}")
async def delete_profile(item_id: str, request: Request) -> dict:
    request.app.state.container.profile_repo().delete(item_id)
    return {"deleted": True}
