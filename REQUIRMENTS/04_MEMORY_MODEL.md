# DOCUMENT 04 — MEMORY MODEL
## Multi-Tier Memory System, Schemas, Lifecycle
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. MEMORY ARCHITECTURE OVERVIEW

Mnemosyne uses a **four-tier memory system** inspired by cognitive science but engineered for practical AI agent use.

```
TIER 1: WORKING MEMORY
├── Active session state
├── Current conversation context
└── Temporary variables
TTL: Minutes to hours

TIER 2: EPISODIC MEMORY  
├── Meaningful events (decisions, milestones, problems)
├── Timestamped, context-rich
└── Links to entities involved
TTL: Weeks to months (decay-governed)

TIER 3: SEMANTIC MEMORY
├── Persistent factual understanding
├── Technical stack, architecture, facts
└── Preferences and behavioral patterns
TTL: Months to permanent (high-importance, slow decay)

TIER 4: PROCEDURAL MEMORY
├── How the user likes to work
├── Workflow patterns
└── Communication preferences
TTL: Semi-permanent (reinforced by repetition)
```

---

## 2. THE MEMORY NODE

Every piece of memory in the system is a **Memory Node**.

### 2.1 Node Schema

```python
@dataclass
class MemoryNode:
    # Identity
    id: str                          # UUID
    workspace_id: str                # Owner workspace
    
    # Classification
    node_type: NodeType              # See 2.2
    tier: MemoryTier                 # WORKING / EPISODIC / SEMANTIC / PROCEDURAL
    
    # Content
    content: str                     # Human-readable description
    structured_data: dict            # Machine-readable structured data
    embedding_vector: List[float]    # For semantic search (384-dim)
    
    # Provenance
    source_platform: str             # claude, chatgpt, gemini, manual
    source_session_id: str           # Which conversation
    extraction_confidence: float     # 0.0 to 1.0
    extracted_at: datetime
    
    # Temporal State
    created_at: datetime
    updated_at: datetime
    valid_from: datetime             # When this version of the fact became true
    valid_until: Optional[datetime]  # When it stopped being true (null = still true)
    version: int                     # Version counter (starts at 1)
    
    # Importance & Decay
    importance_score: float          # 0.0 to 1.0
    reinforcement_count: int         # Times this has been confirmed/accessed
    last_accessed: datetime
    decay_rate: float                # How fast this fades (0.01 = slow, 0.3 = fast)
    is_permanent: bool               # User-marked as permanent (no decay)
    
    # Status
    status: NodeStatus               # ACTIVE / ARCHIVED / PENDING_REVIEW / SUPERSEDED
    user_verified: bool              # User explicitly confirmed this
    
    # Relationships (stored as edges, listed here for reference)
    # See EdgeSchema below
    
    # Conflict tracking
    conflicts_with: List[str]        # IDs of conflicting nodes
    resolved_by: Optional[str]       # ID of resolution event
```

### 2.2 Node Types

```python
class NodeType(Enum):
    # Core cognitive types
    GOAL = "goal"                    # What user is trying to achieve
    DECISION = "decision"            # Choice made with reasoning
    TASK = "task"                    # Concrete action item
    PROBLEM = "problem"              # Open issue or blocker
    EVENT = "event"                  # Significant milestone or occurrence
    
    # Knowledge types
    TECHNICAL_FACT = "technical_fact"  # Stack, architecture, config
    ENTITY = "entity"                  # Person, system, tool, concept
    PREFERENCE = "preference"          # How user likes things done
    RELATIONSHIP = "relationship"      # Captures a link as a first-class node
    
    # Meta types
    WORKSPACE_SUMMARY = "workspace_summary"  # Auto-generated summary node
    USER_NOTE = "user_note"                  # Manually entered by user
```

### 2.3 Edge Schema

```python
@dataclass
class MemoryEdge:
    id: str
    workspace_id: str
    
    source_node_id: str
    target_node_id: str
    
    edge_type: EdgeType
    
    label: str                       # Human-readable edge label
    weight: float                    # 0.0 to 1.0 (relationship strength)
    
    created_at: datetime
    valid_from: datetime
    valid_until: Optional[datetime]

class EdgeType(Enum):
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    RELATES_TO = "relates_to"
    SUPERSEDES = "supersedes"
    CAUSED_BY = "caused_by"
    PART_OF = "part_of"
    ASSIGNED_TO = "assigned_to"
    RESOLVED_BY = "resolved_by"
    CONTRADICTS = "contradicts"
    SIMILAR_TO = "similar_to"
```

---

## 3. TIER 1 — WORKING MEMORY

### Purpose
Capture the active state of the current session. Think of it as a scratchpad.

### What Gets Stored
- Current active goal in this conversation
- Entities mentioned in this session
- Temporary constraints ("for this conversation, assume X")
- Unresolved questions raised in session

### Storage
- In-memory Python dict (not persisted to SQLite)
- TTL: session duration (cleared on session end)
- Max size: 50 nodes

### Promotion to Higher Tiers
Working memory nodes are promoted to Episodic or Semantic memory when:
- They are referenced again in a future session
- User explicitly saves them
- Extraction engine marks them as "high persistence"
- Session contains a clear decision or milestone

### Code Pattern
```python
class WorkingMemory:
    def __init__(self, workspace_id: str, session_id: str):
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.nodes: Dict[str, MemoryNode] = {}
        self.created_at = datetime.utcnow()
    
    def add(self, node: MemoryNode) -> None:
        if len(self.nodes) >= MAX_WORKING_MEMORY_SIZE:
            self._evict_least_important()
        self.nodes[node.id] = node
    
    def promote_to_episodic(self, node_id: str) -> MemoryNode:
        node = self.nodes[node_id]
        node.tier = MemoryTier.EPISODIC
        # Persist to SQLite
        return self.graph_store.upsert_node(node)
```

---

## 4. TIER 2 — EPISODIC MEMORY

### Purpose
Store meaningful events with temporal context. Answerable question: "What happened?"

### Characteristics
- Every episode has a timestamp and duration
- Episodes link to entities involved
- Episodes can have outcomes (positive, negative, neutral, unknown)
- Decay applies (reinforced by future references)

### Example Episodes
```json
{
  "id": "ep_001",
  "type": "event",
  "content": "Presented hackathon pitch to judges",
  "structured_data": {
    "outcome": "positive",
    "entities_involved": ["Hackathon 2025", "team_amir", "Dr. Chen"],
    "result": "Advanced to finals",
    "lessons": ["Judges liked the safety angle", "Depth estimation demo was weak"]
  },
  "timestamp": "2025-06-05T14:00:00Z",
  "importance_score": 0.85,
  "decay_rate": 0.05
}
```

```json
{
  "id": "ep_002", 
  "type": "decision",
  "content": "Decided to remove offline mode from MVP",
  "structured_data": {
    "decision": "Remove offline mode",
    "rationale": "Scope too large for hackathon deadline",
    "alternatives_considered": ["Simplified offline mode", "Async sync"],
    "decided_by": "team",
    "reversible": true,
    "reversed_at": null
  },
  "timestamp": "2025-06-03T09:30:00Z",
  "importance_score": 0.80,
  "decay_rate": 0.02
}
```

---

## 5. TIER 3 — SEMANTIC MEMORY

### Purpose
Persistent factual state of the workspace. Answerable question: "What is true right now?"

### Characteristics
- Represents current truth (not history)
- Mutable — updated when facts change
- Old versions preserved via temporal versioning
- Slow decay (high-importance facts almost never fade)

### Example Semantic Nodes
```json
{
  "id": "sm_001",
  "type": "technical_fact",
  "content": "Backend uses PostgreSQL 16",
  "structured_data": {
    "category": "database",
    "technology": "PostgreSQL",
    "version": "16",
    "rationale": "Needed for full-text search and JSONB",
    "alternatives_rejected": ["MongoDB", "MySQL"]
  },
  "version": 2,
  "valid_from": "2025-05-10",
  "previous_versions": [
    {
      "version": 1,
      "content": "Backend uses SQLite",
      "valid_from": "2025-04-01",
      "valid_until": "2025-05-10",
      "change_reason": "Needed concurrent writes"
    }
  ],
  "importance_score": 0.75,
  "decay_rate": 0.01
}
```

---

## 6. TIER 4 — PROCEDURAL MEMORY

### Purpose
How the user works. Behavioral patterns extracted from repeated behavior.

### Characteristics
- Not about what is true, but how to interact effectively
- Built up slowly from many observations
- Very slow decay (reinforced constantly)
- Applied to context injection as behavioral guidelines

### Example Procedural Nodes
```json
{
  "id": "pm_001",
  "type": "preference",
  "content": "User prefers architecture-first planning before implementation",
  "structured_data": {
    "pattern": "architecture_before_implementation",
    "confidence": 0.91,
    "evidence_count": 17,
    "first_observed": "2025-04-15",
    "last_confirmed": "2025-06-07"
  },
  "decay_rate": 0.005,
  "importance_score": 0.88
}
```

```json
{
  "id": "pm_002",
  "type": "preference",
  "content": "User prefers concise technical responses without explanations of basics",
  "structured_data": {
    "pattern": "concise_technical",
    "confidence": 0.87,
    "evidence": "User consistently skips/dismisses explanatory paragraphs",
    "applied_to": "all AI responses"
  }
}
```

---

## 7. TEMPORAL VERSIONING SYSTEM

This is one of the most critical innovations in Mnemosyne.

### Problem
Without versioning, stale facts poison the knowledge graph silently.

Example problem:
- June 1: System stores "Backend: PostgreSQL"
- June 15: Team switches to MongoDB  
- Without versioning: both facts exist, AI gets confused
- With versioning: PostgreSQL fact gets valid_until=June 15, MongoDB fact becomes current

### Implementation

**Every update to a semantic memory node creates a new version:**

```python
def update_node(self, node_id: str, new_content: dict, change_reason: str) -> MemoryNode:
    existing = self.get_node(node_id)
    
    # Archive current version
    archived = existing.copy()
    archived.valid_until = datetime.utcnow()
    archived.status = NodeStatus.SUPERSEDED
    self.store_version(archived)
    
    # Create new version
    new_version = existing.copy()
    new_version.version = existing.version + 1
    new_version.content = new_content['content']
    new_version.structured_data = new_content['structured_data']
    new_version.valid_from = datetime.utcnow()
    new_version.valid_until = None
    new_version.updated_at = datetime.utcnow()
    new_version.change_reason = change_reason
    
    self.store_node(new_version)
    return new_version
```

### Temporal Queries

```python
# Get state of workspace at a specific point in time
def get_workspace_state_at(workspace_id: str, timestamp: datetime) -> List[MemoryNode]:
    return db.query("""
        SELECT * FROM memory_nodes
        WHERE workspace_id = ?
        AND valid_from <= ?
        AND (valid_until IS NULL OR valid_until > ?)
        AND status != 'SUPERSEDED'
    """, workspace_id, timestamp, timestamp)

# Get current state only
def get_current_state(workspace_id: str) -> List[MemoryNode]:
    return db.query("""
        SELECT * FROM memory_nodes
        WHERE workspace_id = ?
        AND valid_until IS NULL
        AND status = 'ACTIVE'
    """, workspace_id)
```

---

## 8. DECAY SYSTEM

### Why Decay Matters
Without decay:
- Memory grows without bound
- Retrieval noise increases
- Low-signal memories compete with high-signal memories
- Contradictions accumulate

### The Decay Formula

```
retention_score = importance × recency_factor × reinforcement_bonus × workspace_relevance

Where:
  importance = base importance score (set at creation, updated by reinforcement)
  
  recency_factor = exp(-decay_rate × days_since_last_access)
  
  reinforcement_bonus = 1 + (0.1 × min(reinforcement_count, 10))
  
  workspace_relevance = 1.0 if workspace is active, 0.5 if inactive, 0.2 if archived
```

### Decay Rates by Node Type

| Node Type | Default Decay Rate | Notes |
|-----------|-------------------|-------|
| Working Memory | N/A | TTL-based, not decay |
| Task (open) | 0.05 | Slow: unresolved tasks persist |
| Task (completed) | 0.15 | Faster: completed tasks fade |
| Decision | 0.02 | Very slow: decisions are historical record |
| Goal (active) | 0.03 | Slow: active goals stay prominent |
| Goal (completed) | 0.20 | Faster: completed goals less relevant |
| Technical Fact | 0.01 | Very slow: architecture facts are durable |
| Event | 0.08 | Medium: events fade gradually |
| Preference | 0.005 | Extremely slow: preferences are durable |
| Problem (open) | 0.04 | Slow: open problems stay relevant |
| Problem (resolved) | 0.12 | Medium: resolved problems fade |

### Decay Actions

When `retention_score` drops below thresholds:

| Score Range | Action |
|------------|--------|
| > 0.6 | Active — retrieved normally |
| 0.4 - 0.6 | Demoted — lower retrieval priority |
| 0.2 - 0.4 | Archived — not retrieved unless explicitly requested |
| < 0.2 | Pruned — moved to cold storage, not retrieved |
| User-marked permanent | Never decays |

### Reinforcement

Every time a memory node is:
- Returned in a retrieval result: +0.05 reinforcement
- User accesses in audit UI: +0.10 reinforcement
- Referenced in a new conversation: +0.20 reinforcement
- User manually confirms: +0.50 reinforcement, set user_verified=True

---

## 9. IMPORTANCE SCORING

Importance is computed at extraction time and updated over time.

### Initial Importance Score

```python
def compute_initial_importance(node: MemoryNode) -> float:
    score = 0.0
    
    # Node type base score
    type_weights = {
        NodeType.DECISION: 0.8,
        NodeType.GOAL: 0.75,
        NodeType.PROBLEM: 0.70,
        NodeType.TECHNICAL_FACT: 0.65,
        NodeType.EVENT: 0.60,
        NodeType.ENTITY: 0.55,
        NodeType.TASK: 0.50,
        NodeType.PREFERENCE: 0.70,
    }
    score = type_weights.get(node.node_type, 0.5)
    
    # Extraction confidence modifier
    score *= (0.7 + 0.3 * node.extraction_confidence)
    
    # Keyword boosters
    high_importance_keywords = [
        "never", "always", "critical", "must", "blocked", 
        "decided", "final", "confirmed", "deadline", "launch"
    ]
    keyword_hits = sum(1 for k in high_importance_keywords if k in node.content.lower())
    score = min(1.0, score + 0.05 * keyword_hits)
    
    # User-entered gets full score
    if node.source_platform == "user_manual":
        score = max(score, 0.9)
    
    return round(score, 3)
```

---

## 10. MEMORY LIFECYCLE DIAGRAM

```
CAPTURE
   ↓
EXTRACTION (with confidence score)
   ↓
├── High confidence → AUTO-COMMIT
│   ↓
│   WORKING MEMORY
│   ↓ (after session ends or promotion criteria met)
│   EPISODIC / SEMANTIC / PROCEDURAL
│   ↓
│   ACTIVE (retrieved, decaying slowly)
│   ↓
│   DEMOTED (lower priority, still retrievable)
│   ↓
│   ARCHIVED (cold, not retrieved by default)
│   ↓
│   PRUNED (cold storage, compacted)
│
└── Low confidence → PENDING REVIEW
    ↓
    User approves → COMMIT → same path above
    User rejects → DISCARD (not stored)
    Timeout (7 days) → AUTO-DISCARD
```
