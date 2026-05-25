# DOCUMENT 07 — DATABASE SCHEMA
## All Tables, Graph Structure, Indexes, Migrations
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. STORAGE OVERVIEW

Mnemosyne uses **two storage systems per workspace:**

| System | Purpose | File |
|--------|---------|------|
| SQLite (SQLCipher) | Knowledge graph, structured data, all nodes/edges | `graph.db` |
| Qdrant (local) | Vector embeddings for semantic search | `vectors/` |

And **two global databases:**

| System | Purpose | File |
|--------|---------|------|
| SQLite | Workspace registry, user preferences, audit log | `global.db` |
| Redis (optional) | Working memory, capture queue | In-memory |

---

## 2. WORKSPACE DATABASE SCHEMA (graph.db)

### 2.1 memory_nodes

```sql
CREATE TABLE memory_nodes (
    -- Identity
    id                  TEXT PRIMARY KEY,          -- UUID v4
    workspace_id        TEXT NOT NULL,
    
    -- Classification  
    node_type           TEXT NOT NULL,             -- See NodeType enum
    tier                TEXT NOT NULL DEFAULT 'EPISODIC',  -- WORKING/EPISODIC/SEMANTIC/PROCEDURAL
    
    -- Content
    content             TEXT NOT NULL,             -- Human-readable description
    structured_data     TEXT,                      -- JSON blob
    embedding_id        TEXT,                      -- Reference to Qdrant point ID
    
    -- Provenance
    source_platform     TEXT,                      -- claude/chatgpt/gemini/manual
    source_session_id   TEXT,
    extraction_confidence REAL DEFAULT 0.0,
    extracted_at        TEXT,                      -- ISO datetime
    
    -- Temporal versioning
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    valid_from          TEXT NOT NULL,             -- When this version became true
    valid_until         TEXT,                      -- When it stopped being true (NULL = current)
    version             INTEGER NOT NULL DEFAULT 1,
    
    -- Importance & decay
    importance_score    REAL NOT NULL DEFAULT 0.5,
    reinforcement_count INTEGER NOT NULL DEFAULT 0,
    last_accessed       TEXT,
    decay_rate          REAL NOT NULL DEFAULT 0.05,
    is_permanent        INTEGER NOT NULL DEFAULT 0,  -- Boolean
    
    -- Status
    status              TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/ARCHIVED/PENDING_REVIEW/SUPERSEDED
    user_verified       INTEGER NOT NULL DEFAULT 0,      -- Boolean
    
    -- Conflict tracking
    conflicts_with      TEXT DEFAULT '[]',         -- JSON array of node IDs
    resolved_by         TEXT,                      -- Resolution event ID
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('ACTIVE', 'ARCHIVED', 'PENDING_REVIEW', 'SUPERSEDED')),
    CONSTRAINT valid_tier CHECK (tier IN ('WORKING', 'EPISODIC', 'SEMANTIC', 'PROCEDURAL')),
    CONSTRAINT valid_scores CHECK (importance_score BETWEEN 0 AND 1 AND extraction_confidence BETWEEN 0 AND 1)
);

-- Indexes
CREATE INDEX idx_nodes_workspace_type ON memory_nodes(workspace_id, node_type);
CREATE INDEX idx_nodes_workspace_status ON memory_nodes(workspace_id, status);
CREATE INDEX idx_nodes_valid_until ON memory_nodes(valid_until);  -- Fast current-state queries
CREATE INDEX idx_nodes_last_accessed ON memory_nodes(last_accessed);
CREATE INDEX idx_nodes_importance ON memory_nodes(importance_score DESC);

-- FTS5 for full-text search
CREATE VIRTUAL TABLE memory_nodes_fts USING fts5(
    id UNINDEXED,
    content,
    structured_data,
    content='memory_nodes',
    content_rowid='rowid'
);

-- Auto-sync FTS
CREATE TRIGGER nodes_ai AFTER INSERT ON memory_nodes BEGIN
    INSERT INTO memory_nodes_fts(rowid, id, content, structured_data)
    VALUES (new.rowid, new.id, new.content, new.structured_data);
END;
CREATE TRIGGER nodes_au AFTER UPDATE ON memory_nodes BEGIN
    INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, id, content, structured_data)
    VALUES ('delete', old.rowid, old.id, old.content, old.structured_data);
    INSERT INTO memory_nodes_fts(rowid, id, content, structured_data)
    VALUES (new.rowid, new.id, new.content, new.structured_data);
END;
```

### 2.2 memory_edges

```sql
CREATE TABLE memory_edges (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    
    source_node_id      TEXT NOT NULL REFERENCES memory_nodes(id),
    target_node_id      TEXT NOT NULL REFERENCES memory_nodes(id),
    
    edge_type           TEXT NOT NULL,
    label               TEXT,
    weight              REAL NOT NULL DEFAULT 1.0,
    
    created_at          TEXT NOT NULL,
    valid_from          TEXT NOT NULL,
    valid_until         TEXT,
    
    CONSTRAINT valid_edge_type CHECK (edge_type IN (
        'DEPENDS_ON', 'BLOCKS', 'RELATES_TO', 'SUPERSEDES',
        'CAUSED_BY', 'PART_OF', 'ASSIGNED_TO', 'RESOLVED_BY',
        'CONTRADICTS', 'SIMILAR_TO'
    ))
);

CREATE INDEX idx_edges_source ON memory_edges(source_node_id);
CREATE INDEX idx_edges_target ON memory_edges(target_node_id);
CREATE INDEX idx_edges_workspace_type ON memory_edges(workspace_id, edge_type);
```

### 2.3 node_versions (Historical Archive)

```sql
CREATE TABLE node_versions (
    id                  TEXT PRIMARY KEY,
    node_id             TEXT NOT NULL,             -- Original node ID
    workspace_id        TEXT NOT NULL,
    version             INTEGER NOT NULL,
    
    -- Full snapshot of node at this version
    content             TEXT NOT NULL,
    structured_data     TEXT,
    importance_score    REAL,
    
    valid_from          TEXT NOT NULL,
    valid_until         TEXT NOT NULL,             -- Always set for archived versions
    
    change_reason       TEXT,                      -- Why this version was superseded
    changed_by          TEXT DEFAULT 'system',     -- 'system' or 'user'
    
    archived_at         TEXT NOT NULL
);

CREATE INDEX idx_versions_node_id ON node_versions(node_id);
CREATE INDEX idx_versions_workspace ON node_versions(workspace_id, node_id);
```

### 2.4 conflict_events

```sql
CREATE TABLE conflict_events (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    
    conflict_type       TEXT NOT NULL,
    
    node_a_id           TEXT NOT NULL,
    node_b_id           TEXT NOT NULL,
    
    similarity_score    REAL,
    contradiction_score REAL,
    
    status              TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/RESOLVED/IGNORED
    
    resolution_strategy TEXT,
    winning_node_id     TEXT,
    archived_node_ids   TEXT DEFAULT '[]',         -- JSON array
    
    auto_resolved       INTEGER DEFAULT 0,
    resolved_by_user    TEXT,
    resolution_evidence TEXT,
    
    detected_at         TEXT NOT NULL,
    resolved_at         TEXT,
    
    CONSTRAINT valid_conflict_type CHECK (conflict_type IN (
        'DIRECT_FACT', 'GOAL_STATE', 'SEMANTIC_DRIFT',
        'PREFERENCE', 'LOGICAL_ERROR', 'ENTITY_DISAMBIGUATION'
    ))
);

CREATE INDEX idx_conflicts_workspace ON conflict_events(workspace_id, status);
```

### 2.5 pending_reviews

```sql
CREATE TABLE pending_reviews (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    
    -- The extraction candidate (not yet committed)
    candidate_type      TEXT NOT NULL,
    candidate_content   TEXT NOT NULL,
    candidate_data      TEXT,                      -- JSON
    candidate_confidence REAL,
    
    source_session_id   TEXT,
    source_platform     TEXT,
    
    created_at          TEXT NOT NULL,
    expires_at          TEXT NOT NULL,             -- Auto-discard after 7 days
    
    status              TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/APPROVED/REJECTED
    reviewed_at         TEXT,
    review_action       TEXT                       -- What user did
);

CREATE INDEX idx_pending_workspace ON pending_reviews(workspace_id, status);
CREATE INDEX idx_pending_expires ON pending_reviews(expires_at);
```

### 2.6 sessions (Capture History)

```sql
CREATE TABLE sessions (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    platform            TEXT NOT NULL,
    
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    
    turn_count          INTEGER DEFAULT 0,
    nodes_extracted     INTEGER DEFAULT 0,
    nodes_pending       INTEGER DEFAULT 0,
    
    -- Working memory snapshot at session end
    working_memory_snapshot TEXT                   -- JSON
);
```

---

## 3. GLOBAL DATABASE SCHEMA (global.db)

### 3.1 workspaces

```sql
CREATE TABLE workspaces (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    
    color               TEXT DEFAULT '#6366F1',    -- Hex color
    icon                TEXT DEFAULT '🧠',          -- Emoji or icon name
    
    created_at          TEXT NOT NULL,
    last_active         TEXT,
    
    status              TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/ARCHIVED/PAUSED
    capture_enabled     INTEGER NOT NULL DEFAULT 1,
    
    tags                TEXT DEFAULT '[]',          -- JSON array
    
    -- Stats (denormalized for performance)
    entity_count        INTEGER DEFAULT 0,
    node_count          INTEGER DEFAULT 0,
    memory_health_score REAL DEFAULT 1.0,
    
    -- Summary embedding ID (for workspace assignment)
    summary_embedding_id TEXT,
    summary_text        TEXT,
    
    CONSTRAINT valid_status CHECK (status IN ('ACTIVE', 'ARCHIVED', 'PAUSED'))
);

CREATE INDEX idx_workspaces_status ON workspaces(status);
CREATE INDEX idx_workspaces_last_active ON workspaces(last_active DESC);
```

### 3.2 user_settings

```sql
CREATE TABLE user_settings (
    key                 TEXT PRIMARY KEY,
    value               TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Default settings (inserted on first run)
INSERT INTO user_settings VALUES
    ('capture_enabled', 'true', CURRENT_TIMESTAMP),
    ('auto_commit_threshold', '0.80', CURRENT_TIMESTAMP),
    ('llm_extraction_enabled', 'true', CURRENT_TIMESTAMP),
    ('local_model', 'phi4-mini', CURRENT_TIMESTAMP),
    ('context_token_budget', '2000', CURRENT_TIMESTAMP),
    ('decay_enabled', 'true', CURRENT_TIMESTAMP),
    ('decay_schedule_hours', '6', CURRENT_TIMESTAMP),
    ('pending_review_expiry_days', '7', CURRENT_TIMESTAMP),
    ('sensitive_data_filter', 'true', CURRENT_TIMESTAMP),
    ('cloud_sync_enabled', 'false', CURRENT_TIMESTAMP),
    ('theme', 'dark', CURRENT_TIMESTAMP),
    ('sidebar_position', 'right', CURRENT_TIMESTAMP);
```

### 3.3 platform_mappings

```sql
CREATE TABLE platform_mappings (
    id                  TEXT PRIMARY KEY,
    platform            TEXT NOT NULL,             -- claude/chatgpt/gemini
    workspace_id        TEXT NOT NULL,
    url_pattern         TEXT,                      -- Optional URL pattern
    priority            INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL
);
```

### 3.4 audit_log

```sql
CREATE TABLE audit_log (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    action              TEXT NOT NULL,
    entity_type         TEXT,                      -- node/workspace/setting
    entity_id           TEXT,
    details             TEXT,                      -- JSON
    initiated_by        TEXT DEFAULT 'system'      -- system/user
);

-- Never deleted, append-only
-- Indexes for query performance
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_action ON audit_log(action);
```

---

## 4. GRAPH TRAVERSAL QUERIES (Recursive CTEs)

### Get all nodes connected to a node within N hops

```sql
WITH RECURSIVE connected(node_id, depth, path) AS (
    -- Base case: start node
    SELECT ?, 0, CAST(? AS TEXT)
    
    UNION ALL
    
    -- Recursive case: follow edges
    SELECT 
        CASE 
            WHEN e.source_node_id = c.node_id THEN e.target_node_id
            ELSE e.source_node_id
        END,
        c.depth + 1,
        c.path || ',' || CASE 
            WHEN e.source_node_id = c.node_id THEN e.target_node_id
            ELSE e.source_node_id
        END
    FROM connected c
    JOIN memory_edges e ON (e.source_node_id = c.node_id OR e.target_node_id = c.node_id)
    WHERE c.depth < ?  -- Max hops
    AND e.valid_until IS NULL  -- Only active edges
    AND c.path NOT LIKE '%' || CASE 
        WHEN e.source_node_id = c.node_id THEN e.target_node_id
        ELSE e.source_node_id
    END || '%'  -- No cycles
)
SELECT DISTINCT n.*
FROM connected c
JOIN memory_nodes n ON n.id = c.node_id
WHERE n.status = 'ACTIVE'
AND n.valid_until IS NULL
ORDER BY c.depth ASC;
```

### Get workspace state at timestamp

```sql
SELECT *
FROM memory_nodes
WHERE workspace_id = ?
AND valid_from <= ?
AND (valid_until IS NULL OR valid_until > ?)
AND status != 'SUPERSEDED'
ORDER BY importance_score DESC;
```

### Get high-priority retrieval set (for context injection)

```sql
SELECT n.*,
    (n.importance_score 
     * (1.0 / (1 + (julianday('now') - julianday(n.last_accessed)) * n.decay_rate))
     * (1 + 0.1 * MIN(n.reinforcement_count, 10))) AS retention_score
FROM memory_nodes n
WHERE n.workspace_id = ?
AND n.status = 'ACTIVE'
AND n.valid_until IS NULL
ORDER BY retention_score DESC
LIMIT ?;
```

---

## 5. MIGRATIONS

```sql
-- Migration 001: Initial schema
-- (Applied on first run)

-- Migration 002: Add embedding_id to nodes
ALTER TABLE memory_nodes ADD COLUMN embedding_id TEXT;

-- Migration 003: Add workspace health score
ALTER TABLE workspaces ADD COLUMN memory_health_score REAL DEFAULT 1.0;

-- All migrations tracked in:
CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
```

---

## 6. BACKUP & INTEGRITY

```python
# Daily backup
def backup_workspace(workspace_id: str) -> str:
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_path = f"~/.mnemosyne/backups/{workspace_id}_{timestamp}.db"
    
    # SQLite online backup (doesn't lock main db)
    conn = sqlite3.connect(f"~/.mnemosyne/workspaces/{workspace_id}/graph.db")
    backup = sqlite3.connect(backup_path)
    conn.backup(backup)
    backup.close()
    
    return backup_path

# Integrity check (run weekly)
def check_integrity(workspace_id: str) -> IntegrityReport:
    conn = get_connection(workspace_id)
    
    results = conn.execute("PRAGMA integrity_check").fetchall()
    orphaned_edges = conn.execute("""
        SELECT e.id FROM memory_edges e
        LEFT JOIN memory_nodes n ON n.id = e.source_node_id
        WHERE n.id IS NULL
    """).fetchall()
    
    return IntegrityReport(
        sqlite_ok=results[0][0] == 'ok',
        orphaned_edge_count=len(orphaned_edges)
    )
```
