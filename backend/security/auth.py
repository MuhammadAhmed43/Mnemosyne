"""Bearer-token auth dependency (Doc 08 §2, Doc 13 §3.3)."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request


async def verify_token(request: Request, authorization: str = Header(default="")) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization[7:]
    expected = request.app.state.container.config.auth_token
    if not (expected and secrets.compare_digest(token, expected)):
        raise HTTPException(status_code=401, detail="Invalid token")
