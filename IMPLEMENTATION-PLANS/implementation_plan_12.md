# Plan 12 — My Additions & Enhancements

> Covers: 12 features beyond the 18 requirement docs (listed in Plan 00 §My Additions). These are engineering enhancements that make Mnemosyne significantly more powerful.

---

## 1. CONVERSATION THREAD TRACKING

Link related nodes extracted from the same conversation into a "thread" for richer graph traversal.

### backend/models/thread.py
```python
class ConversationThread(BaseModel):
    id: str                     # thread_xxx
    workspace_id: str
    session_id: str
    platform: str
    started_at: datetime
    ended_at: Optional[datetime]
    turn_count: int
    node_ids: List[str]         # All nodes extracted from this thread
    summary: Optional[str]      # Auto-generated after thread ends

class ThreadEdge(BaseModel):
    """Links nodes within the same thread for temporal traversal."""
    thread_id: str
    node_id: str
    turn_index: int             # Which turn produced this node
```

### Schema addition
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

CREATE TABLE thread_nodes (
    thread_id       TEXT NOT NULL REFERENCES conversation_threads(id),
    node_id         TEXT NOT NULL REFERENCES memory_nodes(id),
    turn_index      INTEGER NOT NULL,
    PRIMARY KEY (thread_id, node_id)
);
CREATE INDEX idx_thread_nodes_thread ON thread_nodes(thread_id);
```

### Service logic
```python
# In extraction_worker: after extracting nodes from a capture,
# link them to the active thread for that session.
async def link_to_thread(session_id: str, workspace_id: str, node_ids: List[str], turn_index: int):
    thread = await thread_repo.get_or_create(session_id, workspace_id)
    for nid in node_ids:
        await thread_repo.add_node(thread.id, nid, turn_index)
    thread.turn_count = turn_index + 1
    await thread_repo.update(thread)
```

**Value:** "Show me everything from yesterday's Claude session" becomes a single query. Session Replay (feature #12) builds on this.

---

## 2. SMART CONTEXT TEMPLATES

Per-platform context formatting — different AI platforms expect context differently.

### backend/services/context_templates.py
```python
PLATFORM_TEMPLATES = {
    'claude': {
        'wrapper': '[MNEMOSYNE — Workspace: {workspace_name}]\n\n{content}\n\n[End Mnemosyne Context]',
        'injection_method': 'system_prompt_prepend',
        'max_tokens': 4000,
    },
    'chatgpt': {
        'wrapper': '# Context from Mnemosyne\n## Workspace: {workspace_name}\n\n{content}',
        'injection_method': 'hidden_system_message',
        'max_tokens': 3000,
    },
    'gemini': {
        'wrapper': '<context source="mnemosyne" workspace="{workspace_name}">\n{content}\n</context>',
        'injection_method': 'system_instructions',
        'max_tokens': 3000,
    },
}

def format_context_for_platform(workspace_name: str, content: str, platform: str) -> str:
    template = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES['claude'])
    return template['wrapper'].format(workspace_name=workspace_name, content=content)
```

Integrated into `RetrievalService._build_context_string()` — already receives `platform` param.

---

## 3. MEMORY SNAPSHOTS (Markdown Export)

Point-in-time workspace snapshots exportable as human-readable markdown.

### backend/services/snapshot_service.py
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
    async def export_markdown(self, workspace_id: str) -> str:
        ws = await self.workspace_repo.get(workspace_id)
        nodes = await self.node_repo.get_all_active(workspace_id)
        grouped = group_by(nodes, lambda n: n.node_type)

        lines = [
            f"# Workspace: {ws.name}",
            f"## Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total memories:** {len(nodes)}\n",
        ]

        section_order = [NodeType.GOAL, NodeType.DECISION, NodeType.PROBLEM,
                         NodeType.TECHNICAL_FACT, NodeType.EVENT, NodeType.ENTITY,
                         NodeType.PREFERENCE, NodeType.TASK]

        for ntype in section_order:
            items = grouped.get(ntype, [])
            if not items: continue
            lines.append(f"### {TYPE_LABELS[ntype]} ({len(items)})")
            for node in sorted(items, key=lambda n: -n.importance_score):
                date = node.created_at.strftime('%b %d')
                extra = ""
                if ntype == NodeType.DECISION and node.structured_data.get('rationale'):
                    extra = f" — {node.structured_data['rationale']}"
                if ntype == NodeType.GOAL:
                    status = node.structured_data.get('status', 'ACTIVE')
                    extra = f" [{status}]"
                lines.append(f"- {node.content} ({date}){extra}")
            lines.append("")

        return "\n".join(lines)
```

### API route
```python
@router.get("/api/v1/workspaces/{workspace_id}/snapshot")
async def export_snapshot(workspace_id: str, format: str = "markdown"):
    if format == "markdown":
        content = await snapshot_service.export_markdown(workspace_id)
        return Response(content, media_type="text/markdown",
                       headers={"Content-Disposition": f"attachment; filename={workspace_id}_snapshot.md"})
    # JSON export already exists in workspace routes
```

---

## 4. WORKSPACE TEMPLATES

Pre-built workspace archetypes with suggested node categories.

### backend/services/workspace_templates.py
```python
WORKSPACE_TEMPLATES = {
    "research_project": {
        "name_suffix": "Research",
        "description": "Academic or independent research project",
        "suggested_categories": ["hypothesis", "methodology", "finding", "reference"],
        "default_tags": ["research"],
        "icon": "🔬",
    },
    "startup": {
        "name_suffix": "Startup",
        "description": "Startup or product development",
        "suggested_categories": ["mvp", "market", "investor", "milestone"],
        "default_tags": ["startup", "product"],
        "icon": "🚀",
    },
    "client_work": {
        "name_suffix": "Client Project",
        "description": "Client-facing project or consulting",
        "suggested_categories": ["deliverable", "requirement", "stakeholder"],
        "default_tags": ["client"],
        "icon": "💼",
    },
    "learning": {
        "name_suffix": "Learning",
        "description": "Course, tutorial, or self-study",
        "suggested_categories": ["concept", "exercise", "question"],
        "default_tags": ["learning"],
        "icon": "📚",
    },
    "blank": {
        "name_suffix": "",
        "description": "Start from scratch",
        "suggested_categories": [],
        "default_tags": [],
        "icon": "📝",
    },
}

async def create_from_template(template_key: str, name: str, description: str) -> Workspace:
    template = WORKSPACE_TEMPLATES[template_key]
    ws = await workspace_service.create(
        name=name, description=description,
        icon=template["icon"], tags=template["default_tags"]
    )
    return ws
```

Surfaced in the UI during workspace creation as a template selector grid.

---

## 5. EXTRACTION FEEDBACK LOOP

When user edits/rejects an extraction, feed that signal back to improve future confidence.

### backend/services/feedback_service.py
```python
class ExtractionFeedbackService:
    """Tracks user corrections to tune confidence thresholds over time."""

    async def record_feedback(self, node_id: str, action: str, original: dict, corrected: Optional[dict]):
        """
        action: 'approved', 'edited', 'rejected'
        """
        await self.feedback_repo.insert({
            "node_id": node_id,
            "action": action,
            "original_type": original.get("node_type"),
            "original_confidence": original.get("confidence"),
            "corrected_type": corrected.get("node_type") if corrected else None,
            "timestamp": datetime.utcnow(),
        })

    async def get_adjusted_thresholds(self) -> dict:
        """Analyze feedback history to suggest threshold adjustments."""
        stats = await self.feedback_repo.get_stats()

        adjustments = {}
        for node_type, data in stats.items():
            rejection_rate = data["rejected"] / max(data["total"], 1)
            edit_rate = data["edited"] / max(data["total"], 1)

            # If rejection rate > 20%, raise auto-commit threshold for this type
            if rejection_rate > 0.20:
                adjustments[node_type] = {"auto_commit": min(0.95, 0.80 + rejection_rate * 0.3)}
            # If edit rate > 30%, confidence scoring may be miscalibrated
            elif edit_rate > 0.30:
                adjustments[node_type] = {"auto_commit": min(0.90, 0.80 + edit_rate * 0.2)}

        return adjustments
```

### Schema
```sql
CREATE TABLE extraction_feedback (
    id                  TEXT PRIMARY KEY,
    node_id             TEXT,
    action              TEXT NOT NULL,  -- approved, edited, rejected
    original_type       TEXT,
    original_confidence REAL,
    corrected_type      TEXT,
    timestamp           TEXT NOT NULL
);
CREATE INDEX idx_feedback_type ON extraction_feedback(original_type);
```

---

## 6. KEYBOARD-FIRST COMMAND PALETTE (Cmd+K)

Already outlined in Plan 07 components. Full implementation:

### extension/components/CommandPalette.tsx
```tsx
const ACTIONS = [
  { id: 'search', label: 'Search memories', icon: '🔍', action: () => switchTab('search') },
  { id: 'switch-ws', label: 'Switch workspace', icon: '🧭', action: openWorkspaceSwitcher },
  { id: 'toggle-capture', label: 'Toggle capture', icon: '⏸', action: toggleCapture },
  { id: 'open-dashboard', label: 'Open Memory Audit', icon: '📊', action: openDashboard },
  { id: 'add-node', label: 'Add manual memory', icon: '➕', action: openQuickAdd },
  { id: 'export', label: 'Export workspace', icon: '📦', action: exportWorkspace },
  { id: 'graph', label: 'View graph', icon: '🕸', action: () => switchTab('graph') },
  { id: 'settings', label: 'Settings', icon: '⚙️', action: openSettings },
]

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)

  // Cmd+K / Ctrl+K to open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const filtered = ACTIONS.filter(a =>
    a.label.toLowerCase().includes(query.toLowerCase())
  )

  if (!open) return null

  return (
    <div className="mn-fixed mn-inset-0 mn-z-50 mn-flex mn-items-start mn-justify-center mn-pt-24"
         onClick={() => setOpen(false)}>
      <div className="mn-w-[400px] mn-bg-bg-secondary mn-rounded-xl mn-shadow-lg mn-border mn-border-border"
           onClick={e => e.stopPropagation()}>
        <input value={query} onChange={e => { setQuery(e.target.value); setSelected(0) }}
          placeholder="Type a command..."
          className="mn-w-full mn-px-4 mn-py-3 mn-bg-transparent mn-border-b mn-border-border mn-outline-none"
          autoFocus
          onKeyDown={e => {
            if (e.key === 'ArrowDown') setSelected(s => Math.min(s + 1, filtered.length - 1))
            if (e.key === 'ArrowUp') setSelected(s => Math.max(s - 1, 0))
            if (e.key === 'Enter' && filtered[selected]) {
              filtered[selected].action()
              setOpen(false)
            }
            if (e.key === 'Escape') setOpen(false)
          }} />
        <div className="mn-max-h-64 mn-overflow-y-auto">
          {filtered.map((action, i) => (
            <button key={action.id}
              className={`mn-w-full mn-flex mn-items-center mn-gap-3 mn-px-4 mn-py-2.5 mn-text-sm
                ${i === selected ? 'mn-bg-bg-hover mn-text-accent' : 'mn-text-text-primary'}`}
              onClick={() => { action.action(); setOpen(false) }}>
              <span>{action.icon}</span> {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
```

---

## 7. GRAPH DIFF VIEW

See what changed in the knowledge graph since last session.

### backend/services/graph_diff_service.py
```python
class GraphDiffService:
    async def get_diff(self, workspace_id: str, since: datetime) -> GraphDiff:
        added = await self.node_repo.get_created_since(workspace_id, since)
        updated = await self.node_repo.get_updated_since(workspace_id, since)
        archived = await self.node_repo.get_archived_since(workspace_id, since)
        conflicts = await self.conflict_repo.get_created_since(workspace_id, since)

        return GraphDiff(
            added=[DiffNode(n.id, n.node_type, n.content, 'added') for n in added],
            updated=[DiffNode(n.id, n.node_type, n.content, 'updated') for n in updated],
            archived=[DiffNode(n.id, n.node_type, n.content, 'archived') for n in archived],
            new_conflicts=len(conflicts),
            since=since,
        )
```

### API + UI
```python
@router.get("/api/v1/workspaces/{workspace_id}/diff")
async def get_graph_diff(workspace_id: str, since: str):
    return await graph_diff_service.get_diff(workspace_id, datetime.fromisoformat(since))
```

Displayed as a "What's New" card on the dashboard Overview page with colored indicators (green=added, blue=updated, gray=archived, red=conflicts).

---

## 8. MULTI-MODEL EMBEDDING SUPPORT

Hot-swap between BGE-M3 and nomic-embed based on hardware.

### backend/services/embedding_service.py — Enhanced
```python
EMBEDDING_MODELS = {
    "bge-m3": {
        "name": "BAAI/bge-m3",
        "dimension": 1024,
        "size_mb": 567,
        "min_ram_gb": 4,
    },
    "nomic-embed": {
        "name": "nomic-ai/nomic-embed-text-v1.5",
        "dimension": 768,
        "size_mb": 274,
        "min_ram_gb": 2,
    },
}

class EmbeddingService:
    async def initialize(self, model_key: Optional[str] = None):
        if not model_key:
            model_key = self._auto_select_model()
        config = EMBEDDING_MODELS[model_key]
        self.model = SentenceTransformer(config["name"])
        self.dimension = config["dimension"]
        logger.info(f"Loaded embedding model: {model_key} (dim={self.dimension})")

    def _auto_select_model(self) -> str:
        ram_gb = psutil.virtual_memory().total / (1024**3)
        if ram_gb >= 8:
            return "bge-m3"
        return "nomic-embed"
```

User can override in settings. When model changes, re-embedding runs in background over 24h. Old embeddings still functional during transition.

---

## 9. OFFLINE EXTENSION BUFFER

When engine is down, buffer captures in IndexedDB and replay on reconnect.

### extension/utils/offlineBuffer.ts
```typescript
const DB_NAME = 'mnemosyne-offline'
const STORE_NAME = 'captures'

class OfflineBuffer {
  private db: IDBDatabase | null = null

  async init() {
    this.db = await openDB(DB_NAME, 1, {
      upgrade(db) { db.createObjectStore(STORE_NAME, { keyPath: 'id' }) }
    })
  }

  async buffer(capture: CapturePayload): Promise<void> {
    const tx = this.db!.transaction(STORE_NAME, 'readwrite')
    await tx.objectStore(STORE_NAME).add({
      id: crypto.randomUUID(),
      capture,
      buffered_at: new Date().toISOString(),
    })
  }

  async flush(): Promise<number> {
    const tx = this.db!.transaction(STORE_NAME, 'readonly')
    const items = await tx.objectStore(STORE_NAME).getAll()

    let sent = 0
    for (const item of items) {
      try {
        await api.capture(item.capture)
        await this.delete(item.id)
        sent++
      } catch { break }  // Engine went down again
    }
    return sent
  }

  async count(): Promise<number> {
    const tx = this.db!.transaction(STORE_NAME, 'readonly')
    return tx.objectStore(STORE_NAME).count()
  }
}

export const offlineBuffer = new OfflineBuffer()
```

Integrated into `background.ts`: if `api.capture()` fails → `offlineBuffer.buffer()`. On health check success after failure → `offlineBuffer.flush()`.

---

## 10. WORKSPACE MERGE

Merge two workspaces when they turn out to be the same project.

### backend/services/merge_service.py
```python
class WorkspaceMergeService:
    async def preview_merge(self, source_id: str, target_id: str) -> MergePreview:
        source_nodes = await self.node_repo.get_all(source_id)
        target_nodes = await self.node_repo.get_all(target_id)
        potential_conflicts = await self._find_cross_conflicts(source_nodes, target_nodes)
        return MergePreview(
            source_node_count=len(source_nodes),
            target_node_count=len(target_nodes),
            potential_conflicts=len(potential_conflicts),
        )

    async def execute_merge(self, source_id: str, target_id: str) -> MergeResult:
        source_nodes = await self.node_repo.get_all(source_id)
        source_edges = await self.edge_repo.get_all(source_id)

        # Move all nodes to target workspace
        moved = 0
        for node in source_nodes:
            node.workspace_id = target_id
            await self.node_repo.update(node)
            # Re-index vector embedding under target workspace
            await self.embedding_service.reindex(node.id, target_id)
            moved += 1

        # Move edges
        for edge in source_edges:
            edge.workspace_id = target_id
            await self.edge_repo.update(edge)

        # Run conflict detection on merged workspace
        await self.conflict_service.scan_workspace(target_id)

        # Archive source workspace
        await self.workspace_repo.archive(source_id)
        await self.audit_log.append("workspace_merged", {
            "source": source_id, "target": target_id, "nodes_moved": moved
        })

        return MergeResult(nodes_moved=moved, source_archived=True)
```

---

## 11. NATURAL LANGUAGE GRAPH QUERY

"What decisions did I make about the database?" → structured graph query.

### backend/services/nl_query_service.py
```python
class NaturalLanguageQueryService:
    async def query(self, workspace_id: str, question: str) -> List[MemoryNode]:
        """Convert natural language to structured graph query using local LLM."""
        prompt = f"""Convert this question into a structured query.
Question: "{question}"

Return JSON:
{{"node_types": ["decision", "goal", ...], "keywords": ["database", ...], "time_filter": "last_30_days" | "all"}}
"""
        parsed = await self.llm.complete_json(prompt)

        # Execute structured query
        results = await self.node_repo.search(
            workspace_id=workspace_id,
            node_types=parsed.get("node_types"),
            keywords=parsed.get("keywords", []),
            time_filter=parsed.get("time_filter", "all"),
        )

        # Re-rank by semantic similarity to original question
        question_embedding = await self.embedding_service.embed(question)
        scored = [(n, cosine_similarity(question_embedding, n.embedding)) for n in results]
        scored.sort(key=lambda x: -x[1])

        return [n for n, _ in scored[:20]]
```

Accessible via sidebar Search tab with a "Ask a question" toggle, and via Command Palette.

---

### backend/repositories/thread_repo.py`


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


## 12. SESSION REPLAY

See which extractions came from which session for full traceability.

### dashboard/pages/SessionReplay.tsx
```tsx
// Builds on Conversation Thread Tracking (feature #1)
export default function SessionReplayPage() {
  const [threads, setThreads] = useState<ConversationThread[]>([])
  const [selectedThread, setSelectedThread] = useState<string | null>(null)
  const [threadNodes, setThreadNodes] = useState<ThreadNode[]>([])

  // List all threads for workspace, sorted by date
  // Click thread → show nodes extracted per turn in timeline format

  return (
    <div className="mn-flex mn-h-full">
      {/* Thread list */}
      <div className="mn-w-[300px] mn-border-r mn-border-border mn-overflow-y-auto">
        {threads.map(t => (
          <ThreadCard key={t.id} thread={t}
            active={selectedThread === t.id}
            onClick={() => { setSelectedThread(t.id); loadThreadNodes(t.id) }} />
        ))}
      </div>

      {/* Thread detail: timeline of turns → extracted nodes */}
      <div className="mn-flex-1 mn-p-6 mn-overflow-y-auto">
        {selectedThread && threadNodes.map(tn => (
          <div key={tn.turn_index} className="mn-mb-6">
            <h3 className="mn-text-xs mn-text-text-tertiary mn-mb-2">Turn {tn.turn_index + 1}</h3>
            {tn.nodes.map(node => (
              <MemoryNodeCard key={node.id} node={node} compact />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
```

Added as a sub-page under dashboard: `/sessions`.

---

## Files Summary

| File | Purpose |
|------|---------|
| `backend/models/thread.py` | ConversationThread model |
| `backend/services/context_templates.py` | Platform-specific formatting |
| `backend/services/snapshot_service.py` | Markdown export |
| `backend/services/workspace_templates.py` | Workspace archetypes |
| `backend/services/feedback_service.py` | Extraction feedback loop |
| `backend/services/graph_diff_service.py` | Graph diff since last visit |
| `backend/services/merge_service.py` | Workspace merge |
| `backend/services/nl_query_service.py` | Natural language graph query |
| `backend/repositories/thread_repo.py` | Thread DB access |
| `backend/repositories/feedback_repo.py` | Feedback DB access |
| `extension/components/CommandPalette.tsx` | Cmd+K command palette |
| `extension/utils/offlineBuffer.ts` | IndexedDB offline buffer |
| `dashboard/pages/SessionReplay.tsx` | Session replay view |

**Total: ~13 files.**

---

## COMPLETE PLAN INDEX

| Plan | Title | Files | Status |
|------|-------|-------|--------|
| 00 | Master Index, Architecture & File Structure | — | ✅ |
| 01 | Models, Config & Database Schema | ~18 | ✅ |
| 02 | Extraction Pipeline | ~7 | ✅ |
| 03 | Knowledge Graph & Core Services | ~11 | ✅ |
| 04 | API Layer & Background Workers | ~19 | ✅ |
| 05 | Retrieval & Context Engine | ~6 | ✅ |
| 06 | Chrome Extension Core | ~12 | ✅ |
| 07 | Extension UI: Sidebar & Popup | ~18 | ✅ |
| 08 | Memory Audit Dashboard | ~19 | ✅ |
| 09 | Onboarding & Cold Start | ~13 | ✅ |
| 10 | Testing & Benchmarks | ~25 | ✅ |
| 11 | Deployment, CI/CD & Installers | ~14 | ✅ |
| 12 | My Additions & Enhancements | ~13 | ✅ |

**Grand total: ~175 source files across all plans.**
