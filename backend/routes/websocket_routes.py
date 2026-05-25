"""WebSocket event stream (Doc 08 §12).

Single-consumer in v1 (one extension client). Token is passed as a query param
since browsers can't set Authorization headers on WebSocket handshakes.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/events")
async def events(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    expected = ws.app.state.container.config.auth_token
    if not (expected and secrets.compare_digest(token, expected)):
        await ws.close(code=1008)
        return
    await ws.accept()
    bus = ws.app.state.container.events
    try:
        while True:
            event = await bus.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
