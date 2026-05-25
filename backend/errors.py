"""Structured error type + handler (Doc 08 §13)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.utils.time import now_utc

# Error codes (Doc 08 §13)
INVALID_REQUEST = ("INVALID_REQUEST", 400)
UNAUTHORIZED = ("UNAUTHORIZED", 401)
NOT_FOUND = ("NOT_FOUND", 404)
WORKSPACE_FULL = ("WORKSPACE_FULL", 409)
SENSITIVE_DATA = ("SENSITIVE_DATA", 422)
QUEUE_FULL = ("QUEUE_FULL", 503)
ENGINE_ERROR = ("ENGINE_ERROR", 500)


class MnemosyneError(Exception):
    def __init__(self, code_status: tuple[str, int], message: str, details: dict | None = None):
        self.code, self.status = code_status
        self.message = message
        self.details = details or {}
        super().__init__(message)


async def mnemosyne_error_handler(_request: Request, exc: MnemosyneError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "timestamp": now_utc().isoformat(),
            }
        },
    )
