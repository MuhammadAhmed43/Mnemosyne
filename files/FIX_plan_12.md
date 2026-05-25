# FIX — Plan 12: My Additions & Enhancements
## Fixes for C-12 and C-13
---

## HOW TO USE THIS FILE
Two SQL schema changes — both surgical. No service logic changes needed.

---

## FIX C-12 — Remove impossible cross-database FOREIGN KEY from `conversation_threads`
**File to edit:** Wherever Plan 12 §1 defines the `conversation_threads` SQL schema
(this is a schema addition to the per-workspace `graph.db`)

**Find:**

```sql
CREATE TABLE conversation_threads (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    session_id      TEXT NOT NULL,
    platform        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    turn_count      INTEGER DEFAULT 0,
    summary         TEXT,
    created_at      TEXT NOT NULL
);
```

**Replace with:**

```sql
CREATE TABLE conversation_threads (
    id              TEXT PRIMARY KEY,
    -- workspace_id is stored for scoping/filtering but carries NO foreign key constraint.
    -- REASON: conversation_threads lives in graph.db (per-workspace database).
    -- The workspaces table lives in global.db (a separate SQLite file).
    -- SQLite cannot enforce REFERENCES constraints across separate database files —
    -- even with PRAGMA foreign_keys=ON, cross-file FKs are silently ignored.
    -- Workspace existence is enforced at the application layer in ThreadRepository
    -- (call workspace_repo.get() and raise WorkspaceNotFoundError before inserting here).
    -- (Ref: Doc 03 §6 storage architecture, C-12 conflict report)
    workspace_id    TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    platform        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    turn_count      INTEGER DEFAULT 0,
    summary         TEXT,
    created_at      TEXT NOT NULL
);
-- Index for the most common query: "all threads for this workspace"
CREATE INDEX idx_threads_workspace ON conversation_threads(workspace_id, started_at DESC);
```

**Also check `thread_nodes` — it has `REFERENCES conversation_threads(id)` which IS valid
since both tables are in the same `graph.db` file. That reference is correct, leave it:**

```sql
-- This FK is fine — both tables are in the same graph.db file
CREATE TABLE thread_nodes (
    thread_id       TEXT NOT NULL REFERENCES conversation_threads(id),
    node_id         TEXT NOT NULL REFERENCES memory_nodes(id),
    turn_index      INTEGER NOT NULL,
    PRIMARY KEY (thread_id, node_id)
);
CREATE INDEX idx_thread_nodes_thread ON thread_nodes(thread_id);
```

**Application-layer enforcement to add in `backend/repositories/thread_repository.py`:**

```python
async def get_or_create(self, session_id: str, workspace_id: str) -> ConversationThread:
    """Application-layer workspace existence check before any INSERT.
    This replaces the DB-level FK constraint that cannot exist cross-file.
    """
    # Validate workspace exists (enforces the constraint the FK can't)
    workspace = await self.workspace_repo.get(workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError(workspace_id)

    existing = await self._get_by_session(session_id)
    if existing:
        return existing

    thread = ConversationThread(
        session_id=session_id,
        workspace_id=workspace_id,
        platform=...,
        started_at=datetime.utcnow(),
    )
    await self._insert(thread)
    return thread
```

**Why:** `conversation_threads` is added to `graph.db` (the per-workspace database), but
`workspaces` lives in `global.db` (a separate file). SQLite's `REFERENCES` clause across
separate database files is silently ignored even with `PRAGMA foreign_keys=ON`. The constraint
creates a false sense of referential integrity that doesn't actually exist at the DB level —
a developer debugging a "workspace not found" bug would not find a FK violation, making it
harder to trace. The fix removes the clause and adds a comment + application-layer guard that
provides the same protection correctly. (Ref: Doc 03 §6, Doc 07 §3 architecture, C-12 report)

---

## FIX C-13 — `workspace_snapshots` belongs in graph.db, not global.db

**Context:** The conflict report (C-13) flags `workspace_snapshots` being placed in `global.db`.
Looking at Plan 12 §3, there is no `workspace_snapshots` table being created — the Snapshot
feature is implemented as a pure in-memory computation via `SnapshotService.export_markdown()`
with no persistent table. C-13 is a **pre-emptive architectural guard** rather than a fix to
existing code.

The concern is valid: if a future developer adds a `workspace_snapshots` table to cache
snapshot results, they might follow the wrong pattern from other global tables.

**Add this comment to `backend/services/snapshot_service.py` at the top of the class:**

```python
class SnapshotService:
    """Generates on-demand markdown exports of workspace memory state.

    ARCHITECTURE NOTE (Doc 03 §6, C-13):
    Snapshots are per-workspace data. If a persistent caching table is ever added
    for this feature (e.g. to store snapshot history), it MUST go in the
    per-workspace graph.db — NOT in global.db.

    global.db: workspace registry, global settings, audit log, network activity
    graph.db:  all workspace-scoped data (nodes, edges, versions, conflicts,
               sessions, threads, and any future snapshot cache)

    Placing workspace-scoped data in global.db violates Doc 03 §6 and Doc 14 §2
    (workspace isolation law).
    """

    async def export_markdown(self, workspace_id: str) -> str:
        # ... existing implementation unchanged
```

**Why:** Plan 12 §3 does not currently create a `workspace_snapshots` DB table, so there
is no runtime bug. However, the conflict analysis correctly identifies this as an
architectural risk. Adding the comment makes the constraint explicit for any developer who
extends this service with persistence in the future. (Ref: Doc 03 §6, Doc 14 §2, C-13 report)

---

## No other changes needed in Plan 12.
