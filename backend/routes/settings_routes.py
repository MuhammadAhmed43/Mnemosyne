"""User settings (Doc 08 §10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.models.settings import UserSettings
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["settings"], dependencies=[Depends(verify_token)])


@router.get("/settings", response_model=UserSettings)
async def get_settings(request: Request) -> UserSettings:
    return request.app.state.container.settings_repo.get_user_settings()


@router.put("/settings", response_model=UserSettings)
async def update_settings(settings: UserSettings, request: Request) -> UserSettings:
    request.app.state.container.settings_repo.save_user_settings(settings)
    return settings
