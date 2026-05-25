"""WebSocket event stream (Doc 08 §12).

Single-consumer in v1 (one extension client). Token is passed as a query param
since browsers can't set Authorization headers on WebSocket handshakes.
"""

from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/events")
async def events(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    container = ws.app.state.container
    expected = container.config.auth_token
    if not (expected and secrets.compare_digest(token, expected)):
        await ws.close(code=1008)
        return
    await ws.accept()
    # Each client gets its own queue fed by the broadcaster, so multiple clients
    # (dashboard + chat tab) all receive every event instead of stealing from a
    # shared bus.
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
    container.subscribers.add(queue)
    try:
        while True:
            await ws.send_json(await queue.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        container.subscribers.discard(queue)
