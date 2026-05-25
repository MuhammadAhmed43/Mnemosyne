# DOCUMENT 03 — SYSTEM ARCHITECTURE
## Full System Design, Layers, Data Flow
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. ARCHITECTURE PHILOSOPHY

**Three laws that govern every architectural decision:**

1. **Local before remote** — if it can run on device, it runs on device
2. **Extract before store** — raw data is a liability; structured state is an asset
3. **Workspace before global** — every operation is scoped to a workspace

---

## 2. HIGH-LEVEL SYSTEM MAP

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER DEVICE                              │
│                                                                   │
│  ┌─────────────────┐     ┌─────────────────────────────────────┐│
│  │ BROWSER LAYER   │     │         LOCAL ENGINE                 ││
│  │                 │     │                                       ││
│  │ Chrome Extension│────▶│  ┌─────────────────────────────────┐ ││
│  │ - DOM Observer  │     │  │   CAPTURE GATEWAY               │ ││
│  │ - Message Hook  │     │  │   - Input sanitization          │ ││
│  │ - Injector      │     │  │   - Sensitive data filter       │ ││
│  │ - Sidebar UI    │     │  │   - Workspace router            │ ││
│  │                 │     │  └──────────────┬──────────────────┘ ││
│  └────────┬────────┘     │                 │                     ││
│           │              │  ┌──────────────▼──────────────────┐ ││
│           │              │  │   EXTRACTION ENGINE             │ ││
│           │◀─────────────│  │   - Entity extractor            │ ││
│           │  (injection) │  │   - Goal detector               │ ││
│           │              │  │   - Decision parser             │ ││
│           │              │  │   - Confidence scorer           │ ││
│           │              │  └──────────────┬──────────────────┘ ││
│           │              │                 │                     ││
│           │              │  ┌──────────────▼──────────────────┐ ││
│           │              │  │   COGNITIVE STATE ENGINE        │ ││
│           │              │  │   - Knowledge graph (SQLite)    │ ││
│           │              │  │   - Temporal versioning         │ ││
│           │              │  │   - Contradiction resolver      │ ││
│           │              │  │   - Importance scorer           │ ││
│           │              │  │   - Decay scheduler             │ ││
│           │              │  └──────────────┬──────────────────┘ ││
│           │              │                 │                     ││
│           │              │  ┌──────────────▼──────────────────┐ ││
│           │              │  │   RETRIEVAL ORCHESTRATOR        │ ││
│           │              │  │   - Intent analyzer             │ ││
│           │              │  │   - Graph traversal             │ ││
│           │              │  │   - Semantic search (Qdrant)    │ ││
│           │              │  │   - Context reconstructor       │ ││
│           │              │  └──────────────┬──────────────────┘ ││
│           │              │                 │                     ││
│           │◀─────────────│─────────────────┘                    ││
│           │  (context)   └─────────────────────────────────────┘││
└───────────┼─────────────────────────────────────────────────────┘│
            │                                                        
            ▼ (context injected as system prompt)                   
┌─────────────────────────────────────────────────────────────────┐
│                    AI PLATFORM LAYER                             │
│    Claude.ai    |    ChatGPT    |    Gemini    |    Others        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. COMPONENT BREAKDOWN

### 3.1 Browser Extension (Chrome)
**Technology:** TypeScript, Plasmo Framework, React, Tailwind CSS

**Responsibilities:**
- Observe DOM for AI platform messages
- Intercept send/receive events
- Send raw message pairs to Local Engine via localhost HTTP
- Receive reconstructed context from Local Engine
- Inject context into AI platform (system prompt prepend)
- Render sidebar UI for memory audit
- Handle user preferences and settings

**Communication:**
- Extension → Local Engine: `POST localhost:7432/capture`
- Local Engine → Extension: `GET localhost:7432/context?workspace={id}`
- Extension renders sidebar via React component in injected iframe

**Key Files:**
```
extension/
├── background.ts          # Service worker, lifecycle
├── content/
│   ├── observer.ts        # DOM mutation observer
│   ├── injector.ts        # Context injection logic
│   └── platforms/
│       ├── claude.ts      # Claude.ai-specific hooks
│       ├── chatgpt.ts     # ChatGPT-specific hooks
│       └── gemini.ts      # Gemini-specific hooks
├── sidebar/
│   ├── App.tsx            # Sidebar root
│   ├── WorkspaceView.tsx
│   ├── GraphView.tsx
│   └── AuditView.tsx
└── popup/
    └── Popup.tsx          # Extension popup
```

---

### 3.2 Local Engine (Python FastAPI)
**Technology:** Python 3.11, FastAPI, LangGraph, SQLite, Qdrant (local)

**Runs as:** Background process, auto-started with system (launchd / systemd)

**Port:** 7432 (mnemosyne)

**Responsibilities:**
- Receive captures from extension
- Run extraction pipeline
- Manage knowledge graph
- Run retrieval and context reconstruction
- Serve all API endpoints
- Schedule decay jobs
- Handle conflict resolution

**Process Architecture:**
```
FastAPI App (main thread)
├── /capture endpoint → queue
├── /context endpoint → sync retrieval
└── /audit endpoints → CRUD

Extraction Worker (background thread)
└── Processes capture queue

Decay Scheduler (background thread)
└── Runs every 6 hours

Consolidation Worker (background thread)
└── Runs every 24 hours (dedup, merge)
```

---

### 3.3 Cognitive State Engine
**Technology:** SQLite (graph extension), Custom ORM

**This is the core of the entire system.**

**Manages:**
- Knowledge graph (nodes + edges)
- Temporal versions of every node
- Importance scores
- Decay schedules
- Workspace isolation

**See Document 04 for complete memory model.**

---

### 3.4 Extraction Engine
**Technology:** spaCy (NER), custom rule-based + LLM hybrid

**Pipeline:**
```
Raw Text
   ↓
Preprocessing (clean, normalize)
   ↓
Rule-Based Pass (fast, high precision)
   ↓
NER Pass (spaCy — entities, relationships)
   ↓
LLM Pass (local Phi-4 — goals, decisions, preferences)
   ↓
Confidence Scoring
   ↓
Workspace Assignment
   ↓
Conflict Check
   ↓
Commit or Queue for Review
```

**See Document 06 for complete extraction pipeline.**

---

### 3.5 Retrieval Orchestrator
**Technology:** Qdrant (local), Custom graph traversal, SQLite FTS5

**Pipeline:**
```
New Session Opens
   ↓
Intent Analysis (what is user about to do?)
   ↓
Workspace Detection (which workspace applies?)
   ↓
Multi-Source Retrieval:
   ├── Graph traversal (recent + connected nodes)
   ├── Semantic search (Qdrant local)
   ├── Temporal retrieval (recent decisions/goals)
   └── Priority retrieval (high-importance nodes)
   ↓
Ranking + Deduplication
   ↓
Context Budget Allocation (token budgeting)
   ↓
Context String Construction
   ↓
Return to Extension
```

---

## 4. DATA FLOW — CAPTURE PATH

```
Step 1: User sends message to Claude.ai
        Extension content script detects via DOM mutation

Step 2: Extension captures:
        {
          platform: "claude",
          user_message: "...",
          ai_response: "...",
          timestamp: "...",
          tab_url: "...",
          session_id: "..."
        }

Step 3: Sensitive data filter runs (synchronous, < 10ms)
        If sensitive data detected: STOP, do not proceed

Step 4: HTTP POST to localhost:7432/capture
        Async — does not block user interaction

Step 5: Capture Gateway:
        - Assigns to workspace (existing or suggest new)
        - Queues for extraction worker

Step 6: Extraction Worker processes:
        - Rule-based pass
        - NER pass
        - LLM pass (if needed)
        - Generates extraction candidates

Step 7: Confidence check:
        - High confidence (> threshold) → auto-commit to graph
        - Low confidence → queue for user review

Step 8: Graph write:
        - Create/update nodes
        - Create/update edges
        - Version existing nodes if changed
        - Trigger conflict check

Step 9: Conflict check (see Document 05):
        - If conflict detected → resolution pipeline

Step 10: Update embeddings in Qdrant (async)
```

---

## 5. DATA FLOW — RETRIEVAL PATH

```
Step 1: User opens new AI session
        Extension detects platform URL

Step 2: Extension sends context request:
        GET localhost:7432/context
        {workspace_id, intent_hint, token_budget}

Step 3: Retrieval Orchestrator:
        a. Infer intent from recent activity + tab context
        b. Select workspace
        c. Run multi-source retrieval
        d. Rank results
        e. Build context string within token budget

Step 4: Return context to extension (< 300ms target)

Step 5: Extension injects context into AI platform:
        - Claude: modify system prompt via DOM
        - ChatGPT: inject as first hidden message
        - Gemini: inject via system instructions field

Step 6: Show injection indicator to user
        (collapsible, editable)
```

---

## 6. STORAGE ARCHITECTURE

```
~/.mnemosyne/                        # Root data directory
├── config.json                      # User settings
├── workspaces/
│   ├── {workspace_id}/
│   │   ├── graph.db                 # SQLite knowledge graph
│   │   ├── vectors/                 # Qdrant local storage
│   │   └── audit_log.jsonl          # Append-only audit log
├── global/
│   ├── preferences.db               # Cross-workspace preferences
│   └── workspace_index.db           # Workspace registry
└── temp/
    └── capture_queue/               # Pending extractions (cleared on process)
```

**Why SQLite (not Neo4j for local):**
- Neo4j requires JVM, 500MB+ RAM — unacceptable for local background process
- SQLite with adjacency list pattern supports 99% of graph operations needed
- < 5MB disk footprint for the engine
- Battle-tested reliability
- Graph operations via recursive CTEs (see Document 07)

---

## 7. PROCESS LIFECYCLE

### Startup Sequence
```
System boot / User login
       ↓
Mnemosyne daemon starts (launchd/systemd)
       ↓
Load workspace index
       ↓
Initialize SQLite connections (one per active workspace)
       ↓
Start Qdrant local instance
       ↓
Start FastAPI server on :7432
       ↓
Start background workers (extraction, decay, consolidation)
       ↓
Extension detects engine is alive (health check)
       ↓
System ready
```

### Shutdown / Crash Recovery
- All writes use SQLite WAL mode (no corruption on crash)
- Capture queue is disk-backed (survives crash)
- On restart: replay any unprocessed queue items
- Embeddings regenerated from graph if Qdrant state lost

---

## 8. SECURITY BOUNDARIES

```
TRUST BOUNDARY 1: Extension ↔ Local Engine
- Communication over localhost only (no network)
- Auth token required (generated on install, stored in extension storage)
- HTTPS even on localhost (self-signed cert)

TRUST BOUNDARY 2: Local Engine ↔ Storage
- All SQLite files encrypted (SQLCipher)
- Encryption key derived from user password (optional) or machine key
- No plaintext sensitive data ever written

TRUST BOUNDARY 3: Extension ↔ AI Platform
- Read/write DOM only on allowlisted domains
- No data sent to AI platforms beyond what user typed
- Context injection happens client-side only
```

---

## 9. SCALABILITY DESIGN

### V1 Design Targets
- Up to 1,000,000 memory nodes per user
- Up to 100 active workspaces
- Up to 50 capture events per day
- Up to 10 active workspaces simultaneously

### When to Scale Beyond SQLite
At > 5M nodes per workspace, migrate workspace graph to:
- Option A: DuckDB (still local, columnar, faster analytics)
- Option B: LanceDB (vector-native, still local)
- Option C: Remote Neo4j (only for enterprise multi-user scenarios)

### Memory Budget (RAM)
- Mnemosyne daemon: < 150MB RAM target
- Qdrant local: < 100MB RAM
- SQLite: < 50MB RAM (shared cache)
- Total: < 300MB RAM at rest

---

## 10. EXTENSION ↔ ENGINE API SUMMARY

All communication via localhost:7432

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /capture | Submit conversation turn |
| GET | /context | Get reconstructed context |
| GET | /workspaces | List all workspaces |
| POST | /workspaces | Create workspace |
| GET | /workspaces/{id}/graph | Get graph data |
| GET | /workspaces/{id}/nodes | List memory nodes |
| PUT | /workspaces/{id}/nodes/{nid} | Edit node |
| DELETE | /workspaces/{id}/nodes/{nid} | Delete node |
| GET | /workspaces/{id}/pending | Pending review items |
| POST | /workspaces/{id}/pending/{pid}/approve | Approve extraction |
| POST | /workspaces/{id}/pending/{pid}/reject | Reject extraction |
| GET | /health | Engine health check |
| GET | /settings | Get user settings |
| PUT | /settings | Update settings |

**Full API spec in Document 08.**
