# Plan 01 — Models, Config & Database Schema

> Covers: Doc 04 (Memory Model), Doc 07 (Database Schema), Doc 11 (Tech Stack), Doc 13 (Security)

---

## 1. ENUMS (backend/models/enums.py)

```python
from enum import Enum

class NodeType(str, Enum):
    # Core cognitive types (Doc 04 §2.2)
    GOAL = "goal"                    # What user is trying to achieve
    DECISION = "decision"            # Choice made with reasoning
    TASK = "task"                    # Concrete action item
    PROBLEM = "problem"              # Open issue or blocker
    EVENT = "event"                  # Significant milestone or occurrence

    # Knowledge types
    TECHNICAL_FACT = "technical_fact"  # Stack, architecture, config
    ENTITY = "entity"                  # Person, org, tool, concept
    PREFERENCE = "preference"          # How user likes things done
    RELATIONSHIP = "relationship"      # Captures a link as first-class node

    # Meta types
    WORKSPACE_SUMMARY = "workspace_summary"  # Auto-generated summary node
    USER_NOTE = "user_note"                  # Manually entered by user

    # Extended types (Plan additions)
    OPEN_QUESTION = "open_question"
    INSIGHT = "insight"
    HYPOTHESIS = "hypothesis"
    CONSTRAINT = "constraint"

class MemoryTier(str, Enum):
    WORKING = "working"         # Current session (not persisted)
    EPISODIC = "episodic"       # Specific event/conversation
    SEMANTIC = "semantic"       # Consolidated fact
    PROCEDURAL = "procedural"   # Pattern/workflow

class NodeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    PENDING_REVIEW = "pending_review"
    DECAYED = "decayed"

class EdgeType(str, Enum):
    RELATES_TO = "relates_to"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"              # Doc 04 §2.3 — inverse of DEPENDS_ON
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    PART_OF = "part_of"
    BLOCKED_BY = "blocked_by"
    CAUSED_BY = "caused_by"
    SUPPORTS = "supports"
    ASSIGNED_TO = "assigned_to"    # Doc 04 §2.3
    RESOLVED_BY = "resolved_by"    # Doc 04 §2.3
    SIMILAR_TO = "similar_to"      # Doc 04 §2.3

class ConflictType(str, Enum):
    # Doc 05 §2 — All 6 conflict types (names match Doc 07 §2.4 SQL CHECK constraint)
    DIRECT_FACT = "direct_fact"                       # Type 1: Two nodes assert opposite facts
    GOAL_STATE = "goal_state"                         # Type 2: Goal claimed active AND completed
    SEMANTIC_DRIFT = "semantic_drift"                 # Type 3: Meaning evolved, no explicit update
    PREFERENCE = "preference"                         # Type 4: Contradictory user preferences (Doc 05 §2, Doc 07 §2.4)
    LOGICAL_ERROR = "logical_error"                   # Type 5: Circular/incompatible edges (Doc 05 §2, Doc 07 §2.4)
    ENTITY_DISAMBIGUATION = "entity_disambiguation"   # Type 6: Same name, different things

    # Plan additions (refinements — must be added to SQL CHECK constraint)
    GOAL_CONFLICT = "goal_conflict"                   # Mutual exclusion between goals
    VERSION_FORK = "version_fork"
    SCOPE_CONTRADICTION = "scope_contradiction"
    LOGICAL_INCONSISTENCY = "logical_inconsistency"

class ConflictStrategy(str, Enum):
    TEMPORAL = "temporal"               # Newer wins
    CONFIDENCE_WEIGHTED = "confidence"  # Higher confidence wins
    USER_REVIEW = "user_review"         # Ask user
    PREFERENCE_MERGE = "preference_merge"
    LOGICAL_FLAG = "logical_flag"

class ResolutionStatus(str, Enum):
    PENDING = "pending"
    AUTO_RESOLVED = "auto_resolved"
    USER_RESOLVED = "user_resolved"
    DISMISSED = "dismissed"

class CaptureStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"

class Platform(str, Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    MANUAL = "manual"

class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    PAUSED = "paused"              # Doc 07 §3.1: ACTIVE/ARCHIVED/PAUSED
    DELETED = "deleted"

class CandidateStatus(str, Enum):
    AUTO_COMMITTED = "auto_committed"
    PENDING_REVIEW = "pending_review"
    DISCARDED = "discarded"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"
```

---

## 2. PYDANTIC MODELS

### 2.1 MemoryNode (backend/models/memory_node.py)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from .enums import NodeType, MemoryTier, NodeStatus

class MemoryNode(BaseModel):
    id: str = Field(default_factory=generate_id)
    workspace_id: str
    node_type: NodeType
    tier: MemoryTier = MemoryTier.EPISODIC
    content: str                              # Human-readable summary
    structured_data: dict = {}                # Type-specific payload
    source_session_id: Optional[str] = None
    source_platform: Platform = Platform.MANUAL
    extraction_confidence: float = 1.0        # 0.0-1.0
    extracted_at: Optional[datetime] = None   # Doc 04 §2.1: when extraction occurred
    user_verified: bool = False
    importance_score: float = 0.7             # 0.0-1.0
    decay_rate: float = 0.05                  # Per-day decay constant
    is_permanent: bool = False                # Skip decay if True
    reinforcement_count: int = 0
    status: NodeStatus = NodeStatus.ACTIVE
    version: int = 1
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None    # None = current version
    embedding_id: Optional[str] = None        # Qdrant point ID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    changed_by: str = "system"                # "system" or "user"

    # Conflict tracking (Doc 04 §2.1)
    conflicts_with: list[str] = []            # IDs of conflicting nodes
    resolved_by: Optional[str] = None         # ID of resolution event

class NodeVersion(BaseModel):
    """Immutable historical snapshot of a node at a point in time."""
    id: str
    node_id: str
    workspace_id: str                         # Doc 07 §2.3: required for workspace-scoped queries
    version: int
    content: str
    structured_data: dict
    importance_score: Optional[float] = None  # Doc 07 §2.3: snapshot of importance at that version
    valid_from: datetime
    valid_until: Optional[datetime]
    changed_by: str
    change_reason: Optional[str] = None
    archived_at: datetime = Field(default_factory=datetime.utcnow)  # Doc 07 §2.3: when this version was archived
```

**structured_data shapes by NodeType:**

```python
# GOAL
{"status": "ACTIVE|COMPLETED|ABANDONED", "priority": "HIGH|MEDIUM|LOW",
 "deadline": "2025-06-15", "progress_pct": 0.4}

# DECISION
{"rationale": "...", "alternatives_considered": ["A","B"],
 "reversibility": "HIGH|MEDIUM|LOW"}

# TECHNICAL_FACT
{"entity": "database", "attribute": "technology", "value": "PostgreSQL 16",
 "category": "backend|frontend|infra|ml"}

# ENTITY (Person)
{"entity_type": "person|org|tool|concept", "role": "mentor|teammate|client",
 "contact": null}

# PREFERENCE
{"domain": "communication|code_style|architecture",
 "strength": 0.8, "pattern": "...", "evidence_count": 1}

# TASK
{"status": "TODO|IN_PROGRESS|DONE|BLOCKED",
 "assignee": null, "due_date": null}

# PROBLEM
{"severity": "HIGH|MEDIUM|LOW", "status": "OPEN|RESOLVED",
 "resolution": null}

# EVENT (Doc 04 §4)
{"outcome": "positive|negative|neutral|unknown",
 "entities_involved": ["entity_id_1"],
 "result": "...", "lessons": ["..."]}

# RELATIONSHIP (first-class node for link capture)
{"source_entity": "...", "target_entity": "...",
 "relationship_type": "works_with|reports_to|depends_on"}

# WORKSPACE_SUMMARY (auto-generated)
{"scope": "full|weekly|daily", "generated_at": "...",
 "key_themes": ["..."]}

# USER_NOTE (manually entered)
{"source": "manual", "tags": []}
```

### 2.1b WorkingMemory (backend/models/working_memory.py)

> Doc 04 §3: Working memory is in-memory only (not persisted to SQLite),
> max 50 nodes, with promotion logic to episodic tier.

```python
from typing import Dict, Optional
from .memory_node import MemoryNode
from .enums import MemoryTier

MAX_WORKING_MEMORY_SIZE = 50  # Doc 04 §3

class WorkingMemory:
    """In-memory scratchpad for current session state. Not persisted."""

    def __init__(self, workspace_id: str, session_id: str):
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.nodes: Dict[str, MemoryNode] = {}
        self.created_at = datetime.utcnow()

    def add(self, node: MemoryNode) -> None:
        if len(self.nodes) >= MAX_WORKING_MEMORY_SIZE:
            self._evict_least_important()
        node.tier = MemoryTier.WORKING
        self.nodes[node.id] = node

    def promote_to_episodic(self, node_id: str, graph_store) -> MemoryNode:
        """Promote a working memory node to episodic tier and persist to SQLite."""
        node = self.nodes.pop(node_id)
        node.tier = MemoryTier.EPISODIC
        return graph_store.upsert_node(node)

    def snapshot(self) -> dict:
        """Return JSON-serializable snapshot for sessions.working_memory_snapshot."""
        return {nid: n.content for nid, n in self.nodes.items()}

    def _evict_least_important(self) -> None:
        if not self.nodes:
            return
        least = min(self.nodes.values(), key=lambda n: n.importance_score)
        del self.nodes[least.id]
```

### 2.2 MemoryEdge (backend/models/memory_edge.py)

```python
class MemoryEdge(BaseModel):
    id: str = Field(default_factory=generate_id)
    workspace_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    label: str = ""               # Doc 04 §2.3 — Human-readable edge label
    weight: float = 1.0           # 0.0-1.0 (relationship strength)
    metadata: dict = {}
    is_active: bool = True
    valid_from: datetime = Field(default_factory=datetime.utcnow)   # Doc 04 §2.3
    valid_until: Optional[datetime] = None                          # Doc 04 §2.3 — temporal edge versioning
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2.3 Workspace (backend/models/workspace.py)

```python
class Workspace(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    description: str = ""
    color: str = "#6366F1"                    # Doc 07 §3.1: hex color for UI
    icon: str = "🧠"                           # Doc 07 §3.1: emoji or icon name
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    capture_enabled: bool = True              # Doc 07 §3.1: per-workspace capture toggle
    tags: list[str] = []
    entity_count: int = 0                     # Doc 07 §3.1: denormalized entity count
    node_count: int = 0
    memory_health_score: float = 1.0          # Doc 07 §3.1: workspace health indicator
    summary_embedding_id: Optional[str] = None  # Doc 07 §3.1: for workspace auto-detection
    summary_text: Optional[str] = None        # Doc 07 §3.1: human-readable summary
    embedding_model: str = "BGE-M3"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    settings: dict = {}         # Per-workspace overrides
```

### 2.4 Capture Models (backend/models/capture.py)

```python
class CaptureRequest(BaseModel):
    session_id: str
    platform: Platform
    user_message: str            # Max 50,000 chars
    ai_response: str             # Max 50,000 chars
    timestamp: datetime
    tab_url: str
    workspace_id: Optional[str] = None  # Auto-detect if None
    metadata: dict = {}

class CaptureResult(BaseModel):
    capture_id: str
    status: CaptureStatus
    workspace_id: Optional[str] = None
    reason: Optional[str] = None  # e.g. "sensitive_data_detected"

class CaptureRecord(BaseModel):
    """Internal record stored in queue journal."""
    id: str
    session_id: str
    platform: Platform
    user_message: str
    ai_response: str
    workspace_id: str
    status: CaptureStatus
    timestamp: datetime
    metadata: dict = {}
```

### 2.5 Context Models (backend/models/context.py)

```python
class ContextRequest(BaseModel):
    workspace_id: Optional[str] = None  # Auto-detect
    hint: Optional[str] = None          # First user message
    platform: Platform = Platform.CLAUDE
    token_budget: int = 2000
    include_types: Optional[list[NodeType]] = None

class ContextResult(BaseModel):
    workspace_id: str
    workspace_name: str
    context_string: str          # The injected text
    nodes_included: list[ContextNode]
    token_count: int
    retrieval_ms: int
    injection_id: str            # Track this injection

class ContextNode(BaseModel):
    node_id: str
    node_type: NodeType
    content: str
    relevance_score: float
    source: str                  # "goal_priority", "semantic", "recent", etc.
```

### 2.6 Conflict Models (backend/models/conflict.py)

```python
class ConflictCandidate(BaseModel):
    id: str = Field(default_factory=generate_id)
    workspace_id: str
    node_a_id: str
    node_b_id: str
    conflict_type: ConflictType
    contradiction_score: float   # 0.0-1.0
    suggested_strategy: ConflictStrategy
    auto_resolvable: bool
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ResolutionEvent(BaseModel):
    id: str = Field(default_factory=generate_id)
    workspace_id: str                         # Doc 05 §6
    conflict_id: str
    conflict_type: ConflictType               # Doc 05 §6 — type of conflict resolved
    strategy_used: ConflictStrategy
    status: ResolutionStatus
    winning_node_id: Optional[str] = None
    archived_node_ids: list[str] = []
    custom_resolution: Optional[str] = None
    evidence: str = ""                        # Doc 05 §6 — why this resolution was chosen
    confidence: float = 1.0                   # Doc 05 §6 — system's confidence in resolution
    resolved_by: str = "system"               # "system" or user ID
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2.7 Extraction Models (backend/models/extraction.py)

```python
class ExtractionCandidate(BaseModel):
    node_type: NodeType
    content: str
    structured_data: dict = {}
    confidence: float
    source_pass: str             # "rule_based", "ner", "llm"
    evidence: str = ""           # What triggered this extraction

class ExtractionResult(BaseModel):
    capture_id: str
    auto_committed: list[MemoryNode] = []
    pending_review: list[ExtractionCandidate] = []
    discarded: list[ExtractionCandidate] = []
    conflicts_detected: list[ConflictCandidate] = []
    duration_ms: int

class SensitivityCheckResult(BaseModel):
    is_sensitive: bool
    pattern_matched: Optional[str] = None
    # NEVER store the actual matched text
```

### 2.8 Health & Settings (backend/models/health.py, settings.py)

```python
class HealthResponse(BaseModel):
    status: str                  # "healthy" | "degraded" | "unhealthy"
    version: str
    uptime_seconds: int
    database: str                # "ok" | "error"
    vector_store: str
    ollama_available: bool
    queue_depth: int
    active_workspaces: int

class UserSettings(BaseModel):
    token_budget: int = 2000
    auto_commit_threshold: float = 0.80
    min_confidence: float = 0.60
    decay_enabled: bool = True
    cloud_fallback_enabled: bool = False
    capture_enabled: bool = True
    platforms_enabled: list[Platform] = [Platform.CLAUDE, Platform.CHATGPT, Platform.GEMINI]
    embedding_model: str = "BGE-M3"
    custom_blocked_terms: list[str] = []
    show_blocked_notifications: bool = True
```

---

## 3. CONFIG SYSTEM (backend/config.py)

```python
from pathlib import Path
import json, os, platform

def get_data_dir() -> Path:
    """Platform-aware data directory."""
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", "~")) / "Mnemosyne"
    return Path.home() / ".mnemosyne"

class MnemosyneConfig:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 7432
    auth_token: str               # Generated on first run
    tls_cert_path: Path
    tls_key_path: Path
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "phi4-mini"
    embedding_model: str = "BGE-M3"
    fallback_embedding: str = "nomic-embed-text-v1.5"
    log_level: str = "INFO"
    max_capture_queue: int = 100
    backup_retention_days: int = 7
    decay_interval_hours: int = 6
    consolidation_hour: int = 3   # 3am local time

    @classmethod
    def load(cls) -> "MnemosyneConfig":
        config_path = get_data_dir() / "config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text())
            return cls(**data)
        return cls.create_default()

    @classmethod
    def create_default(cls) -> "MnemosyneConfig":
        """First-run: generate token, create dirs, write config."""
        data_dir = get_data_dir()
        for subdir in ["workspaces", "backups", "logs", "tls", "temp"]:
            (data_dir / subdir).mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        config = cls(data_dir=data_dir, auth_token=token, ...)
        config.save()
        return config
```

---

## 4. DATABASE SCHEMA (backend/db/schema.py)

### 4.1 Global Database (global.db)

```sql
-- Workspace registry
CREATE TABLE workspaces (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT DEFAULT '',
    color               TEXT DEFAULT '#6366F1',    -- Doc 07 §3.1: hex color for UI
    icon                TEXT DEFAULT '🧠',          -- Doc 07 §3.1: emoji or icon name
    status              TEXT NOT NULL DEFAULT 'active',
    capture_enabled     INTEGER NOT NULL DEFAULT 1, -- Doc 07 §3.1: per-workspace capture toggle
    tags                TEXT DEFAULT '[]',   -- JSON array
    entity_count        INTEGER DEFAULT 0,   -- Doc 07 §3.1
    node_count          INTEGER DEFAULT 0,
    memory_health_score REAL DEFAULT 1.0,    -- Doc 07 §3.1
    summary_embedding_id TEXT,               -- Doc 07 §3.1: for workspace auto-detection (Doc 10 §8)
    summary_text        TEXT,                -- Doc 07 §3.1
    embedding_model     TEXT DEFAULT 'BGE-M3',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    last_active         TEXT NOT NULL,
    settings            TEXT DEFAULT '{}',   -- JSON
    CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'paused', 'deleted'))
);
CREATE INDEX idx_workspaces_status ON workspaces(status);
CREATE INDEX idx_workspaces_last_active ON workspaces(last_active DESC);

-- Global user settings (key-value)
CREATE TABLE settings (
    key                 TEXT PRIMARY KEY,
    value               TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Global audit log (append-only, hash-chained)
CREATE TABLE audit_log (
    id                  TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    action              TEXT NOT NULL,
    entity_type         TEXT NOT NULL,       -- 'node','edge','workspace','conflict'
    entity_id           TEXT,
    workspace_id        TEXT,
    details             TEXT,                -- JSON
    chain_hash          TEXT NOT NULL        -- SHA-256 of prev + this entry
);
CREATE INDEX idx_audit_ts ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_ws ON audit_log(workspace_id);

-- Onboarding state (from Doc 17)
CREATE TABLE onboarding_state (
    key                 TEXT PRIMARY KEY,
    value               TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE onboarding_events (
    id                  TEXT PRIMARY KEY,
    event_type          TEXT NOT NULL,
    metadata            TEXT,                -- JSON
    timestamp           TEXT NOT NULL
);
CREATE INDEX idx_onboarding_type ON onboarding_events(event_type);
CREATE INDEX idx_onboarding_ts ON onboarding_events(timestamp DESC);

-- Platform mappings — GLOBAL, not per-workspace (Doc 07 §3.3)
-- Needed for cross-workspace URL matching during workspace auto-detection
CREATE TABLE platform_mappings (
    id                  TEXT PRIMARY KEY,
    platform            TEXT NOT NULL,             -- claude/chatgpt/gemini
    workspace_id        TEXT NOT NULL,
    url_pattern         TEXT,                      -- Optional URL pattern
    priority            INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL
);

-- Schema migrations tracking (Doc 07 §5)
CREATE TABLE schema_migrations (
    version             INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    applied_at          TEXT NOT NULL
);

-- Network activity log (from Doc 12, UC-22)
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

### 4.2 Per-Workspace Database (workspaces/{id}/graph.db)

```sql
-- Core knowledge graph nodes
CREATE TABLE memory_nodes (
    id                      TEXT PRIMARY KEY,
    workspace_id            TEXT NOT NULL,
    node_type               TEXT NOT NULL,
    tier                    TEXT NOT NULL DEFAULT 'episodic',
    content                 TEXT NOT NULL,
    structured_data         TEXT DEFAULT '{}',
    source_session_id       TEXT,
    source_platform         TEXT DEFAULT 'manual',
    extraction_confidence   REAL DEFAULT 1.0,
    extracted_at            TEXT,             -- Doc 04 §2.1, Doc 07 §2.1: when extraction occurred
    user_verified           INTEGER DEFAULT 0,
    importance_score        REAL DEFAULT 0.7,
    decay_rate              REAL DEFAULT 0.05,
    is_permanent            INTEGER DEFAULT 0,
    reinforcement_count     INTEGER DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'active',
    version                 INTEGER DEFAULT 1,
    valid_from              TEXT NOT NULL,
    valid_until             TEXT,             -- NULL = current version
    embedding_id            TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    last_accessed           TEXT NOT NULL,
    changed_by              TEXT DEFAULT 'system',
    conflicts_with          TEXT DEFAULT '[]',  -- Doc 04 §2.1: JSON array of conflicting node IDs
    resolved_by_event       TEXT,               -- Doc 04 §2.1: resolution event ID

    -- Constraints (Doc 07 §2.1 + Plan additions noted)
    -- Note: 'decayed' is a Plan addition beyond Doc 04's ACTIVE/ARCHIVED/PENDING_REVIEW/SUPERSEDED
    CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'pending_review', 'superseded', 'decayed')),
    CONSTRAINT valid_tier CHECK (tier IN ('working', 'episodic', 'semantic', 'procedural')),
    CONSTRAINT valid_scores CHECK (importance_score BETWEEN 0 AND 1 AND extraction_confidence BETWEEN 0 AND 1)
);

-- Indexes for performance (from Doc 07)
CREATE INDEX idx_nodes_type ON memory_nodes(node_type);
CREATE INDEX idx_nodes_status ON memory_nodes(status);
CREATE INDEX idx_nodes_tier ON memory_nodes(tier);
CREATE INDEX idx_nodes_importance ON memory_nodes(importance_score DESC);
CREATE INDEX idx_nodes_valid ON memory_nodes(valid_from, valid_until);
CREATE INDEX idx_nodes_session ON memory_nodes(source_session_id);
CREATE INDEX idx_nodes_created ON memory_nodes(created_at DESC);
CREATE INDEX idx_nodes_accessed ON memory_nodes(last_accessed DESC);

-- Full-text search (FTS5)
CREATE VIRTUAL TABLE memory_nodes_fts USING fts5(
    content, structured_data,
    content=memory_nodes, content_rowid=rowid
);

-- Triggers to keep FTS in sync
CREATE TRIGGER nodes_ai AFTER INSERT ON memory_nodes BEGIN
    INSERT INTO memory_nodes_fts(rowid, content, structured_data)
    VALUES (new.rowid, new.content, new.structured_data);
END;
CREATE TRIGGER nodes_ad AFTER DELETE ON memory_nodes BEGIN
    INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, content, structured_data)
    VALUES ('delete', old.rowid, old.content, old.structured_data);
END;
CREATE TRIGGER nodes_au AFTER UPDATE ON memory_nodes BEGIN
    INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, content, structured_data)
    VALUES ('delete', old.rowid, old.content, old.structured_data);
    INSERT INTO memory_nodes_fts(rowid, content, structured_data)
    VALUES (new.rowid, new.content, new.structured_data);
END;

-- Version history (immutable) — Doc 07 §2.3
CREATE TABLE node_versions (
    id                  TEXT PRIMARY KEY,
    node_id             TEXT NOT NULL,
    workspace_id        TEXT NOT NULL,             -- Doc 07 §2.3: workspace-scoped queries
    version             INTEGER NOT NULL,
    content             TEXT NOT NULL,
    structured_data     TEXT DEFAULT '{}',
    importance_score    REAL,                      -- Doc 07 §2.3: snapshot at this version
    valid_from          TEXT NOT NULL,
    valid_until         TEXT NOT NULL,             -- Doc 07 §2.3: always set for archived versions
    change_reason       TEXT,                      -- Why this version was superseded
    changed_by          TEXT DEFAULT 'system',     -- 'system' or 'user'
    archived_at         TEXT NOT NULL,             -- Doc 07 §2.3: when archived
    FOREIGN KEY (node_id) REFERENCES memory_nodes(id)
);
CREATE INDEX idx_versions_node ON node_versions(node_id, version DESC);
CREATE INDEX idx_versions_workspace ON node_versions(workspace_id, node_id);

-- Graph edges
-- Note: Doc 07 §2.2 CHECK constraint lists 10 types. Plan additions (DERIVED_FROM, BLOCKED_BY, SUPPORTS)
-- are included here and must be added to the SQL CHECK constraint.
CREATE TABLE memory_edges (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    source_node_id      TEXT NOT NULL,
    target_node_id      TEXT NOT NULL,
    edge_type           TEXT NOT NULL,
    label               TEXT DEFAULT '',     -- Doc 04 §2.3: human-readable edge label
    weight              REAL DEFAULT 1.0,
    metadata            TEXT DEFAULT '{}',
    is_active           INTEGER DEFAULT 1,
    valid_from          TEXT NOT NULL,       -- Doc 04 §2.3: when this edge became valid
    valid_until         TEXT,                -- Doc 04 §2.3: NULL = still valid
    created_at          TEXT NOT NULL,
    FOREIGN KEY (source_node_id) REFERENCES memory_nodes(id),
    FOREIGN KEY (target_node_id) REFERENCES memory_nodes(id),
    CONSTRAINT valid_edge_type CHECK (edge_type IN (
        'depends_on', 'blocks', 'relates_to', 'supersedes',
        'caused_by', 'part_of', 'assigned_to', 'resolved_by',
        'contradicts', 'similar_to',
        -- Plan additions beyond Doc 07 §2.2:
        'derived_from', 'blocked_by', 'supports'
    ))
);
CREATE INDEX idx_edges_source ON memory_edges(source_node_id);
CREATE INDEX idx_edges_target ON memory_edges(target_node_id);
CREATE INDEX idx_edges_type ON memory_edges(edge_type);
CREATE INDEX idx_edges_workspace_type ON memory_edges(workspace_id, edge_type);

-- Sessions (Doc 07 §2.6)
CREATE TABLE sessions (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    platform            TEXT NOT NULL,
    tab_url             TEXT,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    turn_count          INTEGER DEFAULT 0,           -- Doc 07 §2.6
    capture_count       INTEGER DEFAULT 0,
    extraction_count    INTEGER DEFAULT 0,
    nodes_extracted     INTEGER DEFAULT 0,           -- Doc 07 §2.6
    nodes_pending       INTEGER DEFAULT 0,           -- Doc 07 §2.6
    working_memory_snapshot TEXT,                     -- Doc 07 §2.6: JSON snapshot at session end
    metadata            TEXT DEFAULT '{}'
);

-- Conflict events (Doc 07 §2.4)
CREATE TABLE conflict_events (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    node_a_id           TEXT NOT NULL,
    node_b_id           TEXT NOT NULL,
    conflict_type       TEXT NOT NULL,
    similarity_score    REAL,                -- Doc 07 §2.4: cosine similarity (Method A: > 0.85)
    contradiction_score REAL,                -- Doc 07 §2.4
    status              TEXT NOT NULL DEFAULT 'PENDING',  -- Doc 07 §2.4: PENDING/RESOLVED/IGNORED
    resolution_strategy TEXT,                -- Doc 07 §2.4
    winning_node_id     TEXT,
    archived_node_ids   TEXT DEFAULT '[]',   -- Doc 07 §2.4: JSON array
    auto_resolved       INTEGER DEFAULT 0,   -- Doc 07 §2.4
    resolved_by_user    TEXT,                -- Doc 07 §2.4
    resolution_evidence TEXT,                -- Doc 07 §2.4
    evidence            TEXT DEFAULT '',     -- Doc 05 §6: why this resolution was chosen
    confidence          REAL DEFAULT 1.0,    -- Doc 05 §6: system confidence in resolution
    detected_at         TEXT NOT NULL,       -- Doc 07 §2.4
    resolved_at         TEXT,
    CONSTRAINT valid_conflict_type CHECK (conflict_type IN (
        'DIRECT_FACT', 'GOAL_STATE', 'SEMANTIC_DRIFT',
        'PREFERENCE', 'LOGICAL_ERROR', 'ENTITY_DISAMBIGUATION',
        -- Plan additions:
        'GOAL_CONFLICT', 'VERSION_FORK', 'SCOPE_CONTRADICTION', 'LOGICAL_INCONSISTENCY'
    ))
);
CREATE INDEX idx_conflicts_workspace ON conflict_events(workspace_id, status);

-- Pending reviews (Doc 07 §2.5)
CREATE TABLE pending_reviews (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL,
    candidate_type      TEXT NOT NULL,       -- Doc 07 §2.5: node type of the candidate
    candidate_content   TEXT NOT NULL,       -- Doc 07 §2.5: human-readable content
    candidate_data      TEXT,                -- JSON for structured_data
    candidate_confidence REAL,               -- Doc 07 §2.5
    source_session_id   TEXT,                -- Doc 07 §2.5
    source_platform     TEXT,                -- Doc 07 §2.5
    created_at          TEXT NOT NULL,
    expires_at          TEXT NOT NULL,        -- Auto-expire after 7 days (Doc 04 §10)
    status              TEXT NOT NULL DEFAULT 'PENDING',  -- Doc 07 §2.5: PENDING/APPROVED/REJECTED
    reviewed_at         TEXT,
    review_action       TEXT                 -- Doc 07 §2.5: what user did
);
CREATE INDEX idx_pending_workspace ON pending_reviews(workspace_id, status);
CREATE INDEX idx_pending_expires ON pending_reviews(expires_at);

-- NOTE: platform_mappings is in GLOBAL.DB (Doc 07 §3.3), not per-workspace.
-- It needs cross-workspace URL matching for workspace auto-detection.
```

---

## 5. MIGRATION SYSTEM (backend/db/migrations.py)

```python
MIGRATIONS = [
    ("001_initial", create_initial_schema),
    ("002_add_embedding_id", add_embedding_column),
    ("003_add_health_score", add_health_score_column),
    ("004_add_platform_mappings", create_platform_mappings),
    ("005_add_onboarding_tables", create_onboarding_tables),
]

async def run_migrations(conn, applied: set[str]):
    for name, func in MIGRATIONS:
        if name not in applied:
            func(conn)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)",
                        (name, datetime.utcnow().isoformat()))
            conn.commit()
```

---

## 6. ENCRYPTION (backend/db/encryption.py)

From Doc 13 — two modes:

```python
def derive_encryption_key(user_password: Optional[str] = None) -> str:
    """Machine-key mode (default) or password mode (opt-in)."""
    salt = get_or_create_machine_salt()
    if user_password:
        key = hashlib.pbkdf2_hmac('sha512', user_password.encode(),
                                   salt, iterations=256000)
    else:
        machine_id = get_machine_id()  # platform-specific
        key = hashlib.pbkdf2_hmac('sha512', machine_id.encode(),
                                   salt, iterations=100000)
    return key.hex()[:64]

def configure_sqlcipher(conn, key: str):
    conn.execute(f"PRAGMA key='{key}'")
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    # Required by Doc 13 §3.1 — without this, SQLCipher may silently fall back
    # to a weaker KDF (e.g. PBKDF2_HMAC_SHA1) on older SQLCipher versions.
    conn.execute("PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
```

---

## 7. DB MANAGER (backend/db/manager.py)

```python
class DatabaseManager:
    """Manages per-workspace SQLite connections + global DB."""

    def __init__(self, config: MnemosyneConfig):
        self._config = config
        self._connections: dict[str, Connection] = {}
        self._global_conn: Optional[Connection] = None
        self._encryption_key = derive_encryption_key()

    async def get_workspace_db(self, workspace_id: str) -> Connection:
        if workspace_id not in self._connections:
            db_path = self._config.data_dir / "workspaces" / workspace_id / "graph.db"
            conn = sqlite3.connect(str(db_path))
            configure_sqlcipher(conn, self._encryption_key)
            await run_migrations(conn, self._get_applied(conn))
            self._connections[workspace_id] = conn
        return self._connections[workspace_id]

    async def get_global_db(self) -> Connection:
        if not self._global_conn:
            db_path = self._config.data_dir / "global.db"
            self._global_conn = sqlite3.connect(str(db_path))
            configure_sqlcipher(self._global_conn, self._encryption_key)
        return self._global_conn

    async def create_workspace_db(self, workspace_id: str):
        ws_dir = self._config.data_dir / "workspaces" / workspace_id
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "vectors").mkdir(exist_ok=True)
        conn = await self.get_workspace_db(workspace_id)
        create_workspace_schema(conn)

    async def close_all(self):
        for conn in self._connections.values():
            conn.close()
        if self._global_conn:
            self._global_conn.close()
```

---

## 8. INTEGRITY CHECK (backend/utils/integrity.py)

> Doc 07 §6: Weekly integrity check for orphaned edges and PRAGMA checks.
> Implemented as a utility callable by the cleanup_worker.

```python
from dataclasses import dataclass

@dataclass
class IntegrityReport:
    sqlite_ok: bool
    orphaned_edge_count: int
    orphaned_edge_ids: list[str]

async def check_integrity(conn) -> IntegrityReport:
    """Run PRAGMA integrity_check and detect orphaned edges. Scheduled weekly."""
    results = conn.execute("PRAGMA integrity_check").fetchall()
    orphaned = conn.execute("""
        SELECT e.id FROM memory_edges e
        LEFT JOIN memory_nodes n ON n.id = e.source_node_id
        WHERE n.id IS NULL
        UNION
        SELECT e.id FROM memory_edges e
        LEFT JOIN memory_nodes n ON n.id = e.target_node_id
        WHERE n.id IS NULL
    """).fetchall()
    return IntegrityReport(
        sqlite_ok=results[0][0] == 'ok',
        orphaned_edge_count=len(orphaned),
        orphaned_edge_ids=[r[0] for r in orphaned]
    )
```

---

## Files Created in This Phase

| File | Purpose |
|------|---------|
| `backend/models/__init__.py` | Re-exports all models |
| `backend/models/enums.py` | All enumerations (11 enums) |
| `backend/models/memory_node.py` | MemoryNode + NodeVersion |
| `backend/models/memory_edge.py` | MemoryEdge |
| `backend/models/workspace.py` | Workspace |
| `backend/models/working_memory.py` | WorkingMemory in-memory manager (Doc 04 §3) |
| `backend/models/capture.py` | CaptureRequest/Result/Record |
| `backend/models/context.py` | ContextRequest/Result/Node |
| `backend/models/conflict.py` | ConflictCandidate + ResolutionEvent |
| `backend/models/extraction.py` | ExtractionCandidate/Result + SensitivityCheckResult |
| `backend/models/health.py` | HealthResponse |
| `backend/models/settings.py` | UserSettings |
| `backend/config.py` | MnemosyneConfig + data dir detection |
| `backend/db/__init__.py` | Package init |
| `backend/db/manager.py` | Connection pool + workspace DB lifecycle |
| `backend/db/schema.py` | All CREATE TABLE + indexes + triggers + FTS5 |
| `backend/db/global_db.py` | Global DB init + workspace registry queries |
| `backend/db/migrations.py` | Sequential migration runner |
| `backend/db/encryption.py` | SQLCipher key derivation + configuration |
| `backend/utils/integrity.py` | Weekly integrity check (Doc 07 §6) |

**Total: 20 files in this phase.**

---

> **Next: Plan 02 — Extraction Pipeline** (rule-based, NER, LLM, sensitive filter, confidence scoring, hypothetical detection)
