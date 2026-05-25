# Plan 00 — Master Index, Architecture & File Structure

## Project Identity

**Codename:** Mnemosyne (Greek goddess of memory)  
**One-liner:** A local-first adaptive cognitive state engine that gives AI persistent, structured, evolving workspace memory.

**What it is NOT:** chat history tool, vector DB wrapper, RAG system, note-taking app.  
**What it IS:** cognitive infrastructure layer, workspace-scoped state machine, knowledge graph with temporal versioning, hybrid retrieval orchestrator, privacy-first local engine.

---

## Core Principles (from Doc 14 — Engineering Laws)

1. **Local-first always** — data never leaves device without explicit opt-in
2. **Workspace over global** — every piece of memory belongs to a workspace
3. **Extract, don't store** — never persist raw conversation; always extract structured state
4. **Visible, auditable memory** — users see, edit, delete everything
5. **Decay over accumulation** — unreinforced memory fades
6. **Structure over volume** — 100 structured facts beat 10,000 raw sentences
7. **Speed first** — context injection must feel instant (<300ms)
8. **Fail gracefully** — if uncertain, say so; never hallucinate confidence

---

## High-Level Architecture (from Doc 03)

```
┌─────────────────────────────────────────────────────┐
│                    USER DEVICE                       │
│                                                      │
│  ┌──────────────┐    ┌────────────────────────────┐ │
│  │ CHROME EXT   │    │      LOCAL ENGINE           │ │
│  │              │    │                              │ │
│  │ DOM Observer │───▶│ Capture Gateway              │ │
│  │ Injector     │    │   ↓                          │ │
│  │ Sidebar UI   │    │ Extraction Engine            │ │
│  │ Popup        │◀───│   (Rule + NER + LLM)         │ │
│  │              │    │   ↓                          │ │
│  └──────────────┘    │ Cognitive State Engine       │ │
│                      │   (SQLite Graph + Qdrant)    │ │
│                      │   ↓                          │ │
│                      │ Retrieval Orchestrator       │ │
│                      │   (Intent → Retrieve → Rank) │ │
│                      └────────────────────────────┘ │
│                                                      │
│  Communication: localhost:7432 (HTTPS + Bearer Auth) │
└─────────────────────────────────────────────────────┘
         ↓ context injected as system prompt
┌─────────────────────────────────────────────────────┐
│        AI PLATFORMS (Claude / ChatGPT / Gemini)      │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack Summary (from Doc 11)

### Browser Extension
| Component | Technology | Version |
|-----------|-----------|---------|
| Language | TypeScript | 5.4+ |
| Framework | Plasmo | 0.88.x |
| UI | React 18 | 18.3.x |
| Styling | Tailwind CSS (prefix: `mn-`) | 3.4.x |
| State | Zustand | 4.5.x |
| Graph Viz | Cytoscape.js | 3.29.x |
| Build | Vite (via Plasmo) | — |
| Tests | Vitest | 1.x |

### Local Engine
| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.11.x |
| Web Framework | FastAPI | 0.110+ |
| Agent Orchestration | LangGraph | 0.1+ |
| NLP | spaCy (en_core_web_sm) | 3.7+ |
| Local LLM | Phi-4 Mini via Ollama | — |
| Embeddings | sentence-transformers (BGE-M3) | 2.7.x |
| Vector Store | Qdrant (local mode) | 1.8.x |
| Database | SQLite + SQLCipher (AES-256) | 3.45+ |
| Task Queue | asyncio.Queue (in-process) | stdlib |
| Validation | Pydantic v2 | 2.6.x |
| HTTP Client | httpx | 0.27.x |
| Crypto | cryptography | 42.x |
| Package Mgr | uv | 0.1.x |
| Linting | ruff + mypy --strict | — |
| Tests | pytest 8.x | — |

### Dev Tooling
| Tool | Purpose |
|------|---------|
| pnpm | Node package manager |
| ruff | Python linter (replaces flake8/isort) |
| mypy --strict | Python type checking |
| ESLint + Prettier | TypeScript lint/format |
| Playwright | E2E browser tests |

---

## V1 Feature Scope (from Doc 02)

### Must-Have (V1)
- **F-001** Automatic Capture — silently intercept AI conversations
- **F-002** Workspace Management — create, switch, archive, delete
- **F-003** Cognitive Extraction — 3-pass pipeline (rule + NER + LLM)
- **F-004** Knowledge Graph — versioned, relationship-aware, decaying
- **F-005** Context Reconstruction — auto-inject relevant context
- **F-006** Memory Audit UI — graph/timeline/workspace/pending/decay views
- **F-007** Privacy Controls — per-platform toggles, sensitive data blocking

### Nice-to-Have (V1)
- **F-008** Smart Suggestions — workspace auto-detection
- **F-009** Memory Health Dashboard
- **F-010** Conversation Summarizer (retroactive)
- **F-011** Cross-Workspace Search

### Explicitly NOT V1
Mobile, IDE plugin, multi-user, cloud sync, enterprise, voice, API for 3rd parties

---

## Data Flow: Capture Path (from Doc 03)

```
User sends message → Extension DOM observer detects
  → Sensitive data filter (sync, <10ms)
    → BLOCKED? stop.
    → CLEAN? POST localhost:7432/capture (async)
      → Capture Gateway: assign workspace, queue
        → Extraction Worker: rule → NER → LLM
          → Confidence check
            → HIGH (>0.80): auto-commit to graph
            → LOW (0.60-0.80): queue for user review
            → BELOW 0.60: discard
          → Conflict check (if committed)
          → Update Qdrant embeddings (async)
```

## Data Flow: Retrieval Path (from Doc 03)

```
User opens AI session → Extension detects platform URL
  → GET localhost:7432/context
    → Intent analysis (recent activity + hint)
    → Workspace detection (similarity scoring)
    → Multi-source retrieval (parallel):
        ├── Active goals (always)
        ├── Recent decisions (14 days)
        ├── Open problems
        ├── Semantic search (Qdrant)
        └── High-importance nodes
    → Rank + deduplicate
    → Token budget allocation
    → Build context string
    → Return to extension (<300ms)
  → Inject into AI platform DOM
  → Show injection indicator
```

---

## Storage Layout (from Docs 03, 07)

> **Workspace limit note:** Doc 02 (PRD §F-002) defines the acceptance criteria at **50 active workspaces**.
> Doc 03 (§9) sets the scalability design target at 100. The product-level limit enforced in code is **50**.
> Doc 03's 100 is the outer design ceiling the storage layer must support without degradation.

```
~/.mnemosyne/                          (Windows: %APPDATA%\Mnemosyne\)
├── config.json                        Auth token, version, settings ref
├── salt                               Machine salt for key derivation
├── tls/
│   ├── cert.pem                       Self-signed localhost cert
│   └── key.pem                        Private key
├── global.db                          Workspace registry, user_settings,
│                                      platform_mappings (Doc 07 §3.3),
│                                      audit_log (Doc 07 §3.4),
│                                      onboarding_events (Doc 17 §10),
│                                      schema_migrations (Doc 07 §5)
├── workspaces/
│   └── {workspace_id}/
│       ├── graph.db                   SQLCipher encrypted knowledge graph
│       ├── vectors/                   Qdrant local storage
│       └── audit_log.jsonl            Per-workspace append-only audit
├── backups/                           Daily auto-backups (7 days)
├── logs/
│   ├── engine.log                     Rotated daily, 7 days
│   ├── engine_err.log
│   ├── extraction.log
│   └── audit.jsonl                    Global immutable audit trail (all workspaces)
└── temp/
    └── capture_queue.jsonl            Disk-backed queue (crash recovery)
```

> **Audit log architecture:** Two audit layers exist by design.
> - `workspaces/{id}/audit_log.jsonl` — workspace-scoped actions (node edits, deletions, conflict resolutions)
> - `logs/audit.jsonl` — global immutable trail (cross-workspace, tamper-evident chain per Doc 13 §8)
> Both are append-only. The global log includes a `chain_hash` for integrity verification.

---

## Complete Source File Structure

```
c:\CotrexAI\
├── REQUIRMENTS/                       # Requirement docs (00-17)
│
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── main.py                        # FastAPI entry + lifespan
│   ├── config.py                      # Settings from ~/.mnemosyne/config.json
│   │
│   ├── models/                        # Pydantic models + enums
│   │   ├── __init__.py
│   │   ├── enums.py                   # NodeType, EdgeType, MemoryTier, etc.
│   │   ├── memory_node.py             # MemoryNode, NodeVersion
│   │   ├── memory_edge.py             # MemoryEdge
│   │   ├── workspace.py               # Workspace
│   │   ├── capture.py                 # CaptureRequest/Result/Record
│   │   ├── context.py                 # ContextResult, Intent
│   │   ├── conflict.py                # ConflictCandidate, ResolutionEvent
│   │   ├── extraction.py              # ExtractionCandidate, ExtractedData
│   │   ├── settings.py                # UserSettings
│   │   └── health.py                  # HealthResponse
│   │
│   ├── db/                            # Database management
│   │   ├── __init__.py
│   │   ├── manager.py                 # Connection pool, per-workspace DBs
│   │   ├── schema.py                  # CREATE TABLE, indexes, triggers
│   │   ├── global_db.py              # Global DB init + queries
│   │   ├── migrations.py             # Sequential migration runner
│   │   └── encryption.py             # SQLCipher key derivation
│   │
│   ├── repositories/                  # Data access layer (SQL)
│   │   ├── __init__.py
│   │   ├── node_repo.py              # CRUD nodes, FTS, graph traversal CTEs
│   │   ├── edge_repo.py              # CRUD edges
│   │   ├── workspace_repo.py         # CRUD workspaces
│   │   ├── conflict_repo.py          # CRUD conflict_events
│   │   ├── pending_review_repo.py    # CRUD pending_reviews
│   │   ├── session_repo.py           # CRUD sessions
│   │   ├── audit_repo.py             # Append-only audit log
│   │   ├── settings_repo.py          # User settings KV
│   │   └── onboarding_repo.py        # Onboarding state + events
│   │
│   ├── services/                      # Business logic layer
│   │   ├── __init__.py
│   │   ├── capture_service.py         # Ingest, sanitize, route
│   │   ├── extraction_service.py      # Orchestrate 3-pass pipeline
│   │   ├── graph_service.py           # Knowledge graph ops, traversal
│   │   ├── retrieval_service.py       # Multi-source retrieval + context build
│   │   ├── conflict_service.py        # Detection + resolution strategies
│   │   ├── decay_service.py           # Retention scoring + decay cycles
│   │   ├── consolidation_service.py   # Dedup + merge near-duplicates
│   │   ├── workspace_service.py       # Lifecycle, inference, health
│   │   ├── embedding_service.py       # sentence-transformers + Qdrant
│   │   ├── intent_service.py          # Intent analysis for retrieval
│   │   └── onboarding_service.py      # Cold start, quick-add, nudges
│   │
│   ├── extraction/                    # Cognitive extraction engine
│   │   ├── __init__.py
│   │   ├── pipeline.py                # Main orchestrator (3-pass)
│   │   ├── rule_based.py              # Regex: tech, decisions, goals
│   │   ├── ner_extractor.py           # spaCy NER + relationship
│   │   ├── llm_extractor.py           # Ollama/Phi-4 structured extraction
│   │   ├── sensitive_filter.py        # API keys, PII, credentials
│   │   ├── confidence_scorer.py       # Multi-pass merge + scoring
│   │   └── hypothetical_detector.py   # "what if" / negation filtering
│   │
│   ├── workers/                       # Background async workers
│   │   ├── __init__.py
│   │   ├── extraction_worker.py       # Process capture queue
│   │   ├── decay_worker.py            # Every 6 hours
│   │   ├── consolidation_worker.py    # Daily at 3am
│   │   ├── cleanup_worker.py          # Expire pending reviews
│   │   └── backup_worker.py           # Daily workspace backups
│   │
│   ├── routes/                        # FastAPI route handlers (thin)
│   │   ├── __init__.py
│   │   ├── capture_routes.py          # POST /capture, GET status
│   │   ├── context_routes.py          # GET /context
│   │   ├── workspace_routes.py        # CRUD workspaces
│   │   ├── node_routes.py             # CRUD nodes, boost
│   │   ├── graph_routes.py            # GET graph data for viz
│   │   ├── pending_routes.py          # Approve/reject pending
│   │   ├── conflict_routes.py         # GET conflicts, POST resolve
│   │   ├── settings_routes.py         # GET/PUT settings
│   │   ├── health_routes.py           # GET /health
│   │   ├── export_routes.py           # Export/import workspace JSON
│   │   ├── onboarding_routes.py       # Quick-add, suggest name, retrospective
│   │   └── websocket_routes.py        # WS /ws/events
│   │
│   ├── security/                      # Security layer
│   │   ├── __init__.py
│   │   ├── auth.py                    # Bearer token validation
│   │   ├── tls.py                     # Self-signed cert generation
│   │   └── cors.py                    # Extension-only CORS policy
│   │
│   └── utils/
│       ├── __init__.py
│       ├── ids.py                     # UUID generation
│       ├── tokens.py                  # Token counting (tiktoken)
│       └── logging.py                 # Structured JSON logger
│
├── extension/
│   ├── package.json
│   ├── tsconfig.json
│   ├── plasmo.config.ts
│   ├── tailwind.config.js             # mn- prefix, design tokens
│   │
│   ├── background.ts                  # Service worker lifecycle
│   │
│   ├── content/
│   │   ├── observer.ts                # DOM MutationObserver
│   │   ├── injector.ts                # Context injection into DOM
│   │   └── platforms/
│   │       ├── claude.ts              # Claude.ai selectors + hooks
│   │       ├── chatgpt.ts             # ChatGPT selectors + hooks
│   │       └── gemini.ts              # Gemini selectors + hooks
│   │
│   ├── sidebar/
│   │   ├── index.tsx                  # Sidebar root (injected iframe)
│   │   ├── MemoryTab.tsx
│   │   ├── GraphTab.tsx               # Cytoscape.js graph
│   │   ├── AuditTab.tsx
│   │   └── SearchTab.tsx
│   │
│   ├── popup/
│   │   └── index.tsx                  # 400×600 popup
│   │
│   ├── onboarding/
│   │   └── index.html                 # Full onboarding flow page
│   │
│   ├── components/
│   │   ├── MemoryNodeCard.tsx
│   │   ├── WorkspaceCard.tsx
│   │   ├── ConfidenceBar.tsx
│   │   ├── NodeTypeBadge.tsx
│   │   ├── ConflictCard.tsx
│   │   ├── CommandPalette.tsx
│   │   ├── InjectionIndicator.tsx
│   │   ├── WorkspaceSelector.tsx
│   │   └── SkeletonLoader.tsx
│   │
│   ├── stores/
│   │   └── mnemosyneStore.ts          # Zustand store
│   │
│   ├── api/
│   │   └── client.ts                  # Typed API client (fetch wrapper)
│   │
│   ├── utils/
│   │   ├── sensitiveFilter.ts         # Client-side pre-filter
│   │   └── platformDetector.ts        # Detect AI platform from URL
│   │
│   └── styles/
│       └── design-system.css          # Full design tokens from Doc 09
│
├── dashboard/                         # Full audit page (new tab)
│   ├── index.html
│   ├── app.tsx
│   ├── pages/
│   │   ├── Overview.tsx
│   │   ├── GraphExplorer.tsx
│   │   ├── MemoryBrowser.tsx
│   │   ├── Timeline.tsx
│   │   ├── ConflictManager.tsx
│   │   └── Settings.tsx
│   └── styles/
│       └── dashboard.css
│
├── tests/
│   ├── conftest.py                    # Shared fixtures
│   ├── unit/
│   │   ├── extraction/
│   │   ├── conflict/
│   │   ├── decay/
│   │   ├── retrieval/
│   │   └── api/
│   ├── integration/
│   │   ├── test_capture_pipeline.py
│   │   ├── test_context_retrieval.py
│   │   └── test_conflict_flow.py
│   ├── benchmarks/
│   │   ├── samples/                   # 500 labeled conversation pairs
│   │   ├── labels/
│   │   ├── run_benchmarks.py
│   │   └── targets.json
│   ├── performance/
│   │   └── test_latency.py
│   └── e2e/
│       └── test_capture_flow.py       # Playwright
│
├── scripts/
│   ├── install_windows.ps1
│   ├── install_macos.sh
│   ├── install_linux.sh
│   └── sign_and_notarize.sh
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── publish-extension.yml
│       └── build-installers.yml
│
└── README.md
```

**Total: ~120 source files across backend, extension, dashboard, tests, and scripts.**

---

## Build Order (Phased)

| Phase | What | Files | Depends On |
|-------|------|-------|------------|
| **1A** | Models + Enums + Config | ~12 | Nothing |
| **1B** | DB Schema + Migrations + Encryption | ~6 | 1A |
| **1C** | Repositories (data access) | ~10 | 1B |
| **1D** | Extraction Pipeline | ~7 | 1A |
| **1E** | Core Services | ~11 | 1C + 1D |
| **1F** | Security (auth, TLS, CORS) | ~3 | 1A |
| **1G** | API Routes + main.py + WebSocket | ~14 | 1E + 1F |
| **1H** | Background Workers | ~5 | 1E |
| **2A** | Extension scaffold (Plasmo + stores) | ~6 | 1G running |
| **2B** | DOM observers + platform hooks | ~5 | 2A |
| **2C** | Context injector + indicator | ~3 | 2A |
| **2D** | Sidebar UI (4 tabs) | ~8 | 2A |
| **2E** | Popup UI | ~2 | 2A |
| **2F** | Onboarding flow | ~2 | 2A |
| **3A** | Dashboard audit page | ~8 | 2A |
| **4A** | Test suite + benchmarks | ~15 | All |
| **4B** | CI/CD + installers | ~6 | All |

---

## My Additions (Detailed in Plan 12)

Features I'm adding beyond the 18 requirement docs:

1. **Conversation Thread Tracking** — link related nodes extracted from the same conversation into a "thread" for richer graph traversal
2. **Smart Context Templates** — per-platform context formatting (Claude system prompt vs ChatGPT hidden message vs Gemini system instructions)
3. **Memory Snapshots** — point-in-time workspace snapshots exportable as markdown (for sharing with teammates)
4. **Workspace Templates** — pre-built workspace archetypes ("Research Project", "Startup", "Client Work") with suggested node categories
5. **Extraction Feedback Loop** — when user edits/rejects an extraction, feed that signal back to improve future confidence scoring
6. **Keyboard-First Command Palette** — Cmd+K across all views with fuzzy search
7. **Graph Diff View** — see what changed in your knowledge graph since last session
8. **Multi-Model Embedding Support** — hot-swap between BGE-M3 and nomic-embed based on hardware
9. **Offline Extension Buffer** — when engine is down, buffer captures in IndexedDB and replay on reconnect
10. **Workspace Merge** — merge two workspaces when they turn out to be the same project
11. **Natural Language Graph Query** — "What decisions did I make about the database?" → query graph
12. **Session Replay** — see which extractions came from which session for traceability

---

## Performance Targets (from Doc 14)

| Operation | Target | Hard Limit |
|-----------|--------|------------|
| Context injection | <300ms | 500ms |
| Extraction per turn | <500ms | 1500ms |
| Sidebar load | <300ms | 500ms |
| Graph query (5-hop) | <50ms | 200ms |
| Workspace switch | <100ms | 300ms |
| Sensitive data filter | <10ms | 30ms |
| Full-text search | <100ms | 300ms |
| Engine RAM at rest | <150MB | 300MB |

---

## Next Plans Preview

- **Plan 01** → All Pydantic models, enums, database CREATE TABLEs, config system
- **Plan 02** → Full extraction pipeline (rule + NER + LLM + sensitive filter)
- **Plan 03** → Graph service, conflict resolution, decay, consolidation
- ...through **Plan 12** (my additions)

Say "continue" to get **Plan 01: Models, Config & Database**.
