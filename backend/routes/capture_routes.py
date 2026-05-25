"""Capture endpoint (Doc 08 §3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.errors import INVALID_REQUEST, MnemosyneError
from backend.models.capture import MAX_MESSAGE_CHARS, CaptureRequest, CaptureResult
from backend.security.auth import verify_token

router = APIRouter(prefix="/api/v1", tags=["capture"], dependencies=[Depends(verify_token)])


@router.post("/capture", status_code=202, response_model=CaptureResult)
async def capture(req: CaptureRequest, request: Request) -> CaptureResult:
    if len(req.user_message) > MAX_MESSAGE_CHARS or len(req.ai_response) > MAX_MESSAGE_CHARS:
        raise MnemosyneError(INVALID_REQUEST, "Message exceeds 50,000 characters")
    c = request.app.state.container
    result, record = c.capture_service.ingest(req)
    if record is not None:
        await request.app.state.queue.push(record)
    return result


@router.get("/capture/{capture_id}/status")
async def capture_status(capture_id: str) -> dict:
    # Captures are processed async and not individually tracked post-queue in v1;
    # status is observable via the WS extraction_completed event + node listings.
    return {"capture_id": capture_id, "status": "queued"}
