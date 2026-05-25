from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "healthy"  # healthy | degraded | unhealthy
    version: str = "1.0.0"
    uptime_seconds: int = 0
    database_ok: bool = True
    vector_store_ok: bool = True
    ollama_available: bool = False
    extraction_worker: str = "running"
    decay_worker: str = "running"
    queue_depth: int = 0
    workspace_count: int = 0
    total_node_count: int = 0
    encryption_at_rest: bool = False  # True when DBs are SQLCipher-encrypted (AES-256)
