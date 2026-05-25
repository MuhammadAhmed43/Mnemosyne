# FIX — Plan 04: FastAPI App, Routes & Lifespan
## Fixes for C-04 and C-15
---

## HOW TO USE THIS FILE
Two separate changes across two files. Apply them independently.

---

## FIX C-04 — Remove broken `network_activity_logger` middleware; add call-site logging instead
**Files to edit:** `backend/main.py`, `backend/services/update_service.py`, `backend/extraction/llm_extractor.py`

### Step 1 — Remove the broken middleware from `backend/main.py`

**Find and DELETE this entire block:**

```python
# Network activity logging middleware (Doc 12, UC-22)
@app.middleware("http")
async def network_activity_logger(request: Request, call_next):
    """Log all outgoing network requests to network_activity table."""
    response = await call_next(request)
    # Log only requests that go OUT (to Ollama, etc.) — inbound from extension is internal
    if not request.url.path.startswith("/api"):
        await state.network_repo.log(
            destination=str(request.url),
            purpose="internal_api",
            is_internal=True,
            bytes_sent=int(request.headers.get("content-length", 0))
        )
    return response
```

**Why it's broken:** This middleware wraps *incoming* requests to the FastAPI server (from
the extension), not *outgoing* requests from the engine. `state.network_repo` is never
initialized on `app.state`, so every call to a non-`/api` path crashes with `AttributeError`.
The condition `not request.url.path.startswith("/api")` means it would attempt to log
`/health` and `/ws/events` calls — both of which hit the undefined `state.network_repo`.
(Ref: Doc 13 §6, C-04 conflict report)

### Step 2 — Add call-site logging in `backend/services/update_service.py`

**Find the `check_for_updates` method and add network logging at the outbound call site:**

```python
class UpdateService:
    GITHUB_RELEASES_URL = "https://api.github.com/repos/mnemosyne/engine/releases/latest"

    def __init__(self, network_logger, ...):
        self._network_logger = network_logger  # Injected dependency
        # ... rest of __init__

    async def check_for_updates(self) -> Optional[UpdateInfo]:
        """Check once per day. No user data sent. Non-critical — never crash."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Log the OUTBOUND network call before it happens (Doc 13 §6, UC-22)
                await self._network_logger.log(
                    destination=self.GITHUB_RELEASES_URL,
                    purpose="update_check",
                    is_internal=False,
                    bytes_sent=0
                )
                r = await client.get(self.GITHUB_RELEASES_URL)
                latest = r.json()["tag_name"].lstrip("v")
                current = get_current_version()
                if semver.compare(latest, current) > 0:
                    return UpdateInfo(current=current, latest=latest,
                                     download_url=r.json()["html_url"])
        except Exception:
            pass  # Update check failure is non-critical
        return None
```

### Step 3 — Add call-site logging in cloud LLM fallback path

**In `backend/extraction/llm_extractor.py`, find the cloud fallback HTTP call and add:**

```python
    async def _call_cloud_llm(self, prompt: str) -> str:
        """Cloud LLM fallback — only when user has enabled it and Ollama is unavailable."""
        # Log the outbound call for UC-22 privacy audit (Doc 13 §6)
        await self._network_logger.log(
            destination=self._cloud_endpoint,
            purpose="cloud_llm_fallback",
            is_internal=False,
            bytes_sent=len(prompt.encode())
        )
        # ... rest of HTTP call
```

**Summary:** Network activity logging for outbound calls belongs at the call site (where
the outbound request actually originates), not in an HTTP middleware that sees inbound
requests from the extension. This is the correct pattern per Doc 13 §6.

---

## FIX C-15 — Add missing timestamp index on `network_activity` table
**File to edit:** `backend/db/schema.py`
**Section:** Global Database (global.db) — immediately after the `network_activity` CREATE TABLE

**Find the `network_activity` table definition (at the end of the global schema):**

```sql
CREATE TABLE network_activity (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    destination         TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    is_internal         INTEGER NOT NULL DEFAULT 1,
    bytes_sent          INTEGER DEFAULT 0
);
```

**Replace with:**

```sql
CREATE TABLE network_activity (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    destination         TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    is_internal         INTEGER NOT NULL DEFAULT 1,
    bytes_sent          INTEGER DEFAULT 0
);
-- Required for UC-22 privacy audit queries (Doc 12): ordered-by-time scans
-- without this index become full table scans as network_activity grows.
CREATE INDEX idx_network_ts ON network_activity(timestamp DESC);
```

**Why:** The privacy audit view (Doc 12 UC-22) queries `network_activity ORDER BY timestamp DESC`.
Without this index every query is a full table scan. On an always-on background process this
table accumulates rows quickly (one row per update check per day, plus one per cloud LLM call).
The index costs ~4KB to maintain and makes the audit query O(log n) instead of O(n).
(Ref: Doc 12 UC-22, C-15 conflict report)

---

## No other changes needed in Plan 04.
