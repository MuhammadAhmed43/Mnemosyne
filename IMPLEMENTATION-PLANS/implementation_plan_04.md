# Plan 04 — API Layer & Background Workers

> Covers: Doc 08 (API Design), Doc 10 (Backend Logic), Doc 16 (Deployment)

---

## 1. MAIN.PY — FastAPI Entry Point

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # STARTUP
    config = MnemosyneConfig.load()
    app.state.config = config
    app.state.db = DatabaseManager(config)
    await app.state.db.initialize()

    # Initialize services (dependency injection)
    app.state.embedding_service = EmbeddingService(config.embedding_model)
    app.state.extraction_pipeline = ExtractionPipeline(config)
    # ... all other services

    # Start background workers
    app.state.workers = []
    app.state.workers.append(asyncio.create_task(extraction_worker(app.state)))
    app.state.workers.append(asyncio.create_task(decay_worker(app.state)))
    app.state.workers.append(asyncio.create_task(consolidation_worker(app.state)))
    app.state.workers.append(asyncio.create_task(cleanup_worker(app.state)))
    app.state.workers.append(asyncio.create_task(backup_worker(app.state)))

    # Crash recovery: replay unprocessed captures
    await startup_recovery(app.state)

    logger.info(f"Mnemosyne engine v{config.version} started on {config.host}:{config.port}")
    yield

    # SHUTDOWN
    for worker in app.state.workers:
        worker.cancel()
    await app.state.db.close_all()
    logger.info("Mnemosyne engine stopped")

app = FastAPI(title="Mnemosyne Engine", version="1.0.0", lifespan=lifespan)

# --- Structured error handler (Doc 08 §13) ---
class MnemosyneError(Exception):
    def __init__(self, code: str, message: str, status: int, details: dict = {}):
        self.code = code; self.message = message
        self.status = status; self.details = details

@app.exception_handler(MnemosyneError)
async def mnemosyne_error_handler(request, exc: MnemosyneError):
    """Doc 08 §13 structured error format."""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status, content={
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "timestamp": datetime.utcnow().isoformat()
        }
    })

# Error codes (Doc 08 §13):
# INVALID_REQUEST | UNAUTHORIZED | NOT_FOUND | WORKSPACE_FULL
# SENSITIVE_DATA | QUEUE_FULL | ENGINE_ERROR

# Middleware
app.add_middleware(CORSMiddleware,
    allow_origins=[f"chrome-extension://{EXTENSION_ID}"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"])

# Routes
app.include_router(capture_router, prefix="/api/v1")
app.include_router(context_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(node_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(pending_router, prefix="/api/v1")
app.include_router(conflict_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(health_router)  # No prefix — /health at root
app.include_router(websocket_router)  # /ws/events

if __name__ == "__main__":
    import uvicorn
    config = MnemosyneConfig.load()
    uvicorn.run(app, host=config.host, port=config.port,
                ssl_certfile=str(config.tls_cert_path),
                ssl_keyfile=str(config.tls_key_path))
```

---

## 2. SECURITY (backend/security/)

### auth.py
```python
from fastapi import Depends, HTTPException, Header

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid auth header")
    token = authorization[7:]
    expected = app.state.config.auth_token
    if not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Invalid token")
```

### tls.py
```python
def generate_localhost_cert(tls_dir: Path):
    """Self-signed cert for localhost, valid 10 years."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mnemosyne Local CA")]))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(IPv4Address("127.0.0.1"))
        ]), critical=False)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .public_key(key.public_key())
        .sign(key, hashes.SHA256()))
    # Write to tls_dir/cert.pem and tls_dir/key.pem
```

---

## 3. ALL API ROUTES

### 3.1 capture_routes.py
```python
router = APIRouter(tags=["capture"], dependencies=[Depends(verify_token)])

@router.post("/capture", status_code=202, response_model=CaptureResponse)
async def capture(req: CaptureRequest):
    """Ingest a conversation turn pair. Returns immediately (async processing)."""
    # Validates: message length <= 50,000 chars (413 if exceeded)
    # Doc 08 §3 response contract:
    # {
    #   capture_id: str,
    #   status: "queued" | "blocked" | "skipped",
    #   workspace_id: str | null,
    #   estimated_processing_ms: int,    # ← Doc 08 §3 required field
    #   sensitive_data_detected: bool,   # ← Doc 08 §3 required field
    #   reason: str | null               # Why blocked/skipped
    # }

@router.get("/capture/{capture_id}/status", response_model=CaptureStatusResponse)
async def capture_status(capture_id: str):
    """Poll extraction status for a specific capture."""
    # Doc 08 §3 status response contract:
    # {
    #   capture_id: str,
    #   status: "queued" | "processing" | "completed" | "failed",
    #   auto_committed: int,             # nodes auto-committed
    #   pending_review: int,             # nodes queued for review
    #   processing_time_ms: int,         # actual extraction time
    #   nodes_created: list[str],        # IDs of committed nodes
    #   pending_ids: list[str]           # IDs of pending review items
    # }
```

### 3.2 context_routes.py
```python
@router.get("/context", response_model=ContextResponse)
async def get_context(
    workspace_id: Optional[str] = None,
    intent: Optional[str] = None,
    platform: Platform = Platform.CLAUDE,
    token_budget: int = Query(default=2000, le=4000),
):
    """Retrieve context for injection. <300ms target."""
    # If no workspace_id: auto-detect from intent text
    # Doc 08 §4 response contract:
    # {
    #   workspace: {id: str, name: str},   # ← nested object, not flat workspace_id
    #   context_string: str,
    #   nodes_included: list[ContextNode],
    #   nodes_available: int,              # ← total nodes in workspace (for UI)
    #   token_count: int,
    #   freshness_score: float,            # ← avg recency of included nodes
    #   injection_format: str,             # ← "claude_xml"|"markdown"|"plain"
    #   retrieval_ms: int
    # }
```

### 3.3 workspace_routes.py
```python
@router.post("/workspaces", response_model=Workspace, status_code=201)
async def create_workspace(
    name: str = Body(...), 
    description: str = Body(""), 
    color: str = Body("#6366F1"), 
    icon: str = Body("🧠"), 
    tags: list[str] = Body([])
)

@router.get("/workspaces", response_model=PaginatedWorkspacesResponse)
async def list_workspaces(
    status: Optional[str] = Query(None,
        description="Filter: active | archived | paused | all"),  # Doc 08 §5
    sort: Optional[str] = Query(None,
        description="Sort by: last_active | created_at | name"),  # Doc 08 §5
)

@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str)

@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: str, 
    name: Optional[str] = Body(None), 
    description: Optional[str] = Body(None),
    capture_enabled: Optional[bool] = Body(None),
    color: Optional[str] = Body(None),
    icon: Optional[str] = Body(None),
    tags: Optional[list[str]] = Body(None)
)

@router.post("/workspaces/{workspace_id}/archive")
async def archive_workspace(workspace_id: str)

@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    confirm: bool = Query(..., description="Must be true"),     # Doc 08 §5: required
    export_first: bool = Query(False,
        description="If true, returns JSON export before deleting")  # Doc 08 §5
)
# If export_first=True: generate export, include in response, THEN delete

@router.get("/workspaces/{workspace_id}/health")
async def workspace_health(workspace_id: str)
```

### 3.4 node_routes.py
```python
@router.get("/workspaces/{workspace_id}/nodes", response_model=PaginatedNodesResponse)
async def list_nodes(
    workspace_id: str,
    type: Optional[str] = Query("all", description="goal/decision/task/etc"),
    status: Optional[str] = Query("active", description="active/archived/superseded/all"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),          # Doc 08 §6: pagination
    sort: Optional[str] = Query("importance",
        description="Sort by: importance | created_at | last_accessed"),
    search: Optional[str] = Query(None,
        description="FTS search within results"),  # Doc 08 §6
)
# Response: {total: int, limit: int, offset: int, nodes: list[MemoryNode]}

@router.get("/workspaces/{workspace_id}/nodes/{node_id}", response_model=EnrichedNodeResponse)
async def get_node(workspace_id: str, node_id: str):
    """Doc 08 §6: Enriched single node response."""
    # Returns: {node, version_history[], connected_edges[], conflict_events[]}

@router.put("/workspaces/{workspace_id}/nodes/{node_id}")
async def update_node(
    workspace_id: str,
    node_id: str,
    content: Optional[str] = Body(None),
    structured_data: Optional[dict] = Body(None),
    importance_score: Optional[float] = Body(None),
    is_permanent: Optional[bool] = Body(None)
)
    # Creates new version (temporal versioning), sets changed_by='user'

@router.post("/workspaces/{workspace_id}/nodes/{node_id}/boost")
async def boost_node(
    workspace_id: str,
    node_id: str,
    boost_amount: float = Body(..., ge=0.0, le=1.0,
        description="Additive boost to importance_score (Doc 08 §6)"),
    reason: str = Body("user_explicit",
        description="user_explicit | retrieval_result | manual_review")
)
# Implementation: node.importance_score = min(1.0, node.importance_score + boost_amount)
# NOT a setter — additive semantics per Doc 08 §6

@router.delete("/workspaces/{workspace_id}/nodes/{node_id}")
async def delete_node(workspace_id: str, node_id: str, hard: bool = False)
    # hard=False → archive; hard=True → permanent delete from SQLite + Qdrant

@router.post("/workspaces/{workspace_id}/nodes/bulk-delete")
async def bulk_delete(workspace_id: str, node_ids: list[str] = Body(...), hard: bool = Query(False))

@router.post("/workspaces/{workspace_id}/nodes/manual", response_model=MemoryNode)
async def create_manual_node(
    workspace_id: str, 
    node_type: NodeType = Body(...),
    content: str = Body(...), 
    structured_data: dict = Body({})
)
    # user_verified=True, extraction_confidence=1.0
```

### 3.5 graph_routes.py
```python
@router.get("/workspaces/{workspace_id}/graph")
async def get_graph(
    workspace_id: str,
    max_nodes: int = Query(200, le=1000),
    center_node: Optional[str] = Query(None, description="Return subgraph around this node"),
    hops: int = Query(3, le=5),
    filter_type: Optional[str] = Query("all", description="Filter by node type")
):
    """Full graph data or subgraph for Cytoscape.js visualization (Doc 08 §7)."""
    # Returns: {nodes: [...], edges: [...], node_count: int, edge_count: int}

@router.get("/workspaces/{workspace_id}/search")
async def search(workspace_id: str, q: str):
    """Full-text search via FTS5. <100ms target."""

@router.get("/search/global")
async def global_search(q: str):
    """Cross-workspace search (UC-21)."""
```

### 3.6 pending_routes.py
```python
@router.get("/workspaces/{workspace_id}/pending", response_model=PaginatedPendingResponse)
async def list_pending(workspace_id: str)

@router.post("/workspaces/{workspace_id}/pending/{review_id}/approve")
async def approve_pending(
    workspace_id: str,
    review_id: str,
    edits: Optional[dict] = Body(None, description="Optional edits to content/structured_data")
)
    # If edits provided: commit with user edits. Always user_verified=True.

@router.post("/workspaces/{workspace_id}/pending/{review_id}/reject")
async def reject_pending(
    workspace_id: str,
    review_id: str,
    reason: str = Body(..., description="inaccurate | irrelevant | duplicate | other")
)
```

### 3.7 conflict_routes.py
```python
@router.get("/workspaces/{workspace_id}/conflicts")
async def list_conflicts(workspace_id: str, status: Optional[ResolutionStatus] = None)

@router.post("/workspaces/{workspace_id}/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    workspace_id: str,
    conflict_id: str,
    strategy: str = Body(..., description="keep_a | keep_b | merge | custom"),
    merged_content: Optional[str] = Body(None),
    reason: Optional[str] = Body(None)
)

@router.get("/workspaces/{workspace_id}/conflicts/history")
async def conflict_history(workspace_id: str)
```

### 3.8 settings_routes.py
```python
@router.get("/settings", response_model=UserSettings)
async def get_settings()

@router.put("/settings", response_model=UserSettings)
async def update_settings(settings: UserSettings)
```

### 3.9 export_routes.py
```python
@router.get("/workspaces/{workspace_id}/export")
async def export_workspace(workspace_id: str):
    """Full JSON export: nodes, edges, versions, sessions."""

@router.post("/workspaces/import")
async def import_workspace(data: dict):
    """Import workspace from JSON. Re-generates embeddings."""
```

### 3.10 onboarding_routes.py
```python
@router.post("/onboarding/quick-add")
async def quick_add(workspace_id: str, goal: str = None,
                    tech_stack: str = None, key_person: str = None)

@router.post("/onboarding/suggest-name")
async def suggest_name(description: str) -> dict:
    """LLM-generated workspace name from description."""

@router.post("/onboarding/retrospective")
async def retrospective(raw_text: str, platform: str, workspace_id: str):
    """Import past conversation. All results → pending review."""

@router.post("/onboarding/event")
async def log_onboarding_event(event_type: str, metadata: dict = {})
```

### 3.11 health_routes.py
```python
@router.get("/health", response_model=HealthResponse)
async def health():
    """Polled every 30s by extension. Must respond <100ms. (Doc 08 §11)"""
    return HealthResponse(
        status="healthy", 
        version=config.version,
        uptime_seconds=..., 
        database_ok=True, 
        vector_store_ok=True,
        extraction_worker="running",
        decay_worker="running",
        queue_depth=extraction_queue.qsize(),
        workspace_count=...,
        total_node_count=...
    )
```

### 3.12 websocket_routes.py
```python
@router.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """Real-time event streaming to extension."""
    await ws.accept()
    # Verify token from query param
    # Doc 08 §12 — all event types:
    # extraction_completed  → nodes committed/pending from a capture
    # conflict_detected     → new conflict needs review
    # node_created          → new node committed to graph
    # pending_review_added  → new item in pending queue
    # decay_completed       → decay cycle finished
    # workspace_suggestion  → system detected new project context, suggests new workspace
    while True:
        event = await event_bus.get()
        await ws.send_json(event.dict())
```

---

## 4. BACKGROUND WORKERS

### extraction_worker.py
```python
async def extraction_worker(state):
    """Processes capture queue continuously."""
    queue = state.capture_queue  # asyncio.Queue, disk-backed

    while True:
        capture = await queue.get()
        try:
            result = await state.extraction_pipeline.run(capture)

            # Auto-commit high-confidence
            for candidate in result._routed["auto_commit"]:
                node = await state.graph_service.commit_node(
                    capture.workspace_id, candidate, capture.session_id)
                # Check for conflicts
                conflicts = await state.conflict_service.detect_conflicts(
                    capture.workspace_id, node)
                for conflict in conflicts:
                    if conflict.auto_resolvable:
                        await state.conflict_service.auto_resolve(conflict)
                    else:
                        await state.conflict_repo.create(conflict)

            # Queue pending reviews
            for candidate in result._routed["pending_review"]:
                await state.pending_repo.create(PendingReview(
                    workspace_id=capture.workspace_id,
                    candidate_type=candidate.node_type.value,
                    candidate_content=candidate.content,
                    candidate_data=candidate.model_dump_json(),
                    candidate_confidence=candidate.confidence,
                    source_session_id=capture.session_id,
                    source_platform=capture.platform,
                    source_context=f"{capture.user_message[:200]}\n{capture.ai_response[:200]}",  # Doc 08 §8
                    expires_at=datetime.utcnow() + timedelta(days=7),  # Doc 04 §10: 7-day auto-discard
                ))

            # Emit WebSocket event
            await state.event_bus.put(Event(type="extraction_completed",
                workspace_id=capture.workspace_id,
                data={"auto_committed": len(result._routed["auto_commit"]),
                      "pending": len(result._routed["pending_review"])}))

            # Mark complete in journal
            await state.capture_journal.mark_complete(capture.id)

        except Exception as e:
            logger.error(f"Extraction failed for {capture.id}: {e}")
            # Retry logic: 3 attempts with exponential backoff
            capture.retry_count = getattr(capture, 'retry_count', 0) + 1
            if capture.retry_count < 3:
                await asyncio.sleep(2 ** capture.retry_count)
                await queue.put(capture)
```

### decay_worker.py
```python
async def decay_worker(state):
    """Runs every 6 hours."""
    while True:
        await asyncio.sleep(6 * 3600)  # 6 hours
        for ws in await state.workspace_repo.get_active():
            await state.decay_service.run_decay_cycle(ws.id)
        await state.event_bus.put(Event(type="decay_completed"))
```

### consolidation_worker.py
```python
async def consolidation_worker(state):
    """Runs daily at 3am local time."""
    while True:
        now = datetime.now()
        target = now.replace(hour=3, minute=0, second=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        for ws in await state.workspace_repo.get_active():
            await state.consolidation_service.run_consolidation(ws.id)
```

### cleanup_worker.py
```python
async def cleanup_worker(state):
    """Expires old pending reviews. Runs every hour."""
    while True:
        await asyncio.sleep(3600)
        expired = await state.pending_repo.get_expired()
        for review in expired:
            await state.pending_repo.update_status(review.id, "expired")
```

### backup_worker.py
```python
async def backup_worker(state):
    """Daily workspace backups. Keep 7 days."""
    while True:
        now = datetime.now()
        target = now.replace(hour=2, minute=0)  # 2am
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await backup_all_workspaces(state.config)
```

---

## 5. CAPTURE QUEUE (Disk-Backed)

```python
class DiskBackedQueue:
    """asyncio.Queue with JSONL journal for crash recovery."""

    def __init__(self, journal_path: Path, max_size: int = 100):
        self._queue = asyncio.Queue(maxsize=max_size)
        self._journal_path = journal_path

    async def push(self, capture: CaptureRecord):
        # Write to journal BEFORE queueing
        async with aiofiles.open(self._journal_path, 'a') as f:
            await f.write(capture.model_dump_json() + '\n')
        await self._queue.put(capture)

    async def get(self) -> CaptureRecord:
        return await self._queue.get()

    async def mark_complete(self, capture_id: str):
        # Rewrite journal without completed item
        ...

    async def replay_unprocessed(self) -> int:
        """Called on startup for crash recovery."""
        count = 0
        if self._journal_path.exists():
            async with aiofiles.open(self._journal_path) as f:
                async for line in f:
                    record = CaptureRecord.model_validate_json(line)
                    if record.status == CaptureStatus.QUEUED:
                        await self._queue.put(record)
                        count += 1
        return count
```

---

## 6. LOGGING (backend/utils/logging.py)

```python
import logging, json
from logging.handlers import RotatingFileHandler

def setup_logging(config: MnemosyneConfig):
    """Structured JSON logging. Never log message content."""
    handler = RotatingFileHandler(
        config.data_dir / "logs" / "engine.log",
        maxBytes=10_000_000,  # 10MB
        backupCount=7)

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "component": record.name,
                "event": record.getMessage(),
            })

    handler.setFormatter(JSONFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(getattr(logging, config.log_level))
```

---

## Files Summary

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app + lifespan + middleware |
| `backend/security/__init__.py` | Package |
| `backend/security/auth.py` | Bearer token verification |
| `backend/security/tls.py` | Self-signed cert generation |
| `backend/security/cors.py` | Extension-only CORS |
| `backend/errors.py` | MnemosyneError + error handler + 7 error codes (Doc 08 §13) |
| `backend/routes/capture_routes.py` | POST /capture + GET /capture/{id}/status |
| `backend/routes/context_routes.py` | GET /context |
| `backend/routes/workspace_routes.py` | CRUD workspaces + export-before-delete |
| `backend/routes/node_routes.py` | CRUD nodes + additive boost + paginated list |
| `backend/routes/graph_routes.py` | Graph data + search |
| `backend/routes/pending_routes.py` | Approve/reject |
| `backend/routes/conflict_routes.py` | Conflict management |
| `backend/routes/settings_routes.py` | Settings CRUD |
| `backend/routes/export_routes.py` | Export/import |
| `backend/routes/onboarding_routes.py` | Quick-add, suggest, retro |
| `backend/routes/health_routes.py` | Health check |
| `backend/routes/websocket_routes.py` | WS event streaming (6 event types) |
| `backend/workers/extraction_worker.py` | Queue processor |
| `backend/workers/decay_worker.py` | 6-hour decay cycles |
| `backend/workers/consolidation_worker.py` | Daily 3am consolidation |
| `backend/workers/cleanup_worker.py` | Expire pending reviews |
| `backend/workers/backup_worker.py` | Daily 2am backups |
| `backend/utils/logging.py` | Structured JSON logger |

**Total: ~23 files, ~1,200 lines.**

---

> **Next: Plan 05 — Retrieval & Context Engine**
