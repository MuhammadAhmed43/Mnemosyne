# DOCUMENT 11 — TECH STACK
## Every Tool, Version, Rationale, and Alternative Considered
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. PHILOSOPHY

Every technology decision in Mnemosyne is governed by three constraints:

1. **Runs entirely on user hardware** — no dependency on external services for core functionality
2. **Minimal footprint** — total daemon RAM target < 300MB, no JVM, no heavy runtimes
3. **Battle-tested reliability** — we are not the infrastructure experiment; the memory system is the experiment

---

## 2. BROWSER EXTENSION

### Runtime: TypeScript 5.4+
**Why:** Type safety is non-negotiable for a system that manipulates the DOM and manages complex state. JavaScript silent failures in a memory system are unacceptable. TypeScript catches schema drift, API contract violations, and null-reference bugs at compile time.

**Alternatives rejected:**
- Plain JavaScript — no type safety, error-prone
- ReScript — too niche, poor library ecosystem

---

### Framework: Plasmo 0.x
**Why:** Plasmo is the only production-grade framework specifically designed for Chrome extensions. It handles manifest v3 complexity, hot reload during development, content script injection, and messaging between service workers and content scripts — all things that are extremely tedious to do manually.

**What it solves:**
- Manifest V3 compliance (required by Chrome since 2024)
- TypeScript compilation for extension context
- Cross-browser build targets (Chrome, Edge, Firefox)
- Dev-mode hot reload (critical for extension development velocity)

**Alternatives rejected:**
- Raw Webpack + manifest.json — massive boilerplate, no type-safe messaging
- CRXJS — less mature, smaller community

---

### UI Framework: React 18 + React DOM
**Why:** The sidebar is a complex, stateful UI. React's component model, hooks, and extensive ecosystem (graph libs, animation libs) make it the right choice. React 18's concurrent rendering matters for keeping the sidebar responsive while background extraction runs.

**Alternatives rejected:**
- Svelte — excellent but smaller ecosystem, fewer graph visualization options
- Vue — viable, but team familiarity and ecosystem advantage goes to React

---

### Styling: Tailwind CSS 3.x
**Why:** Utility-first CSS is ideal for component-level UI in extension context. No CSS module conflicts, no global style leakage into the host page, fast iteration. The extension sidebar is injected into third-party pages — utility classes prevent inheritance conflicts.

**Key config:**
```js
// tailwind.config.js
module.exports = {
  prefix: 'mn-',  // Prefix all classes to avoid collision with host page CSS
  ctype: ['./src/**/*.{tsx,ts}'],
  theme: {
    extend: {
      colors: {
        accent: '#7C3AED',
        // ... full design system tokens
      }
    }
  }
}
```

**Alternatives rejected:**
- CSS Modules — verbose for component-level work
- Emotion/styled-components — runtime CSS-in-JS has performance cost in extension context
- Shadow DOM isolation — too complex for the sidebar use case

---

### Graph Visualization: Cytoscape.js 3.x
**Why:** Cytoscape is the most mature, performant graph visualization library for web. It handles 1,000+ node graphs without frame drops, supports custom layouts (force-directed, hierarchical, circular), and has an extensive plugin ecosystem.

**Key features used:**
- Force-directed layout (`cola` layout)
- Custom node styles by type (color, size, shape)
- Edge labels and weights
- Click/hover interaction model
- Export to PNG/SVG

**Alternatives rejected:**
- D3.js force simulation — more control, but far more code; Cytoscape's abstractions are worth the tradeoff
- Vis.js — heavier, performance degrades at node counts we expect
- React Flow — beautiful but designed for flowcharts, not knowledge graphs

---

### State Management: Zustand 4.x
**Why:** Lightweight, TypeScript-first, no boilerplate. Extension state is simple enough that Redux is overkill. Zustand stores are just typed objects with actions — perfect for workspace state, sidebar state, and capture status.

```typescript
interface MnemosyneStore {
  activeWorkspace: Workspace | null;
  captureEnabled: boolean;
  pendingReviewCount: number;
  sidebarOpen: boolean;
  setActiveWorkspace: (ws: Workspace) => void;
  toggleCapture: () => void;
}
```

**Alternatives rejected:**
- Redux Toolkit — overengineered for this scale
- Jotai — viable, but Zustand has better middleware support (devtools, persist)
- Context API — fine for simple cases, but causes unnecessary re-renders at extension scale

---

### Build Tool: Vite (via Plasmo)
**Why:** Plasmo uses Vite under the hood, which provides sub-second hot module replacement, native ESM, and fast production builds. No Webpack configuration hell.

---

## 3. LOCAL ENGINE

### Runtime: Python 3.11
**Why:** The ML/NLP ecosystem is Python-first. spaCy, transformers, sentence-transformers, and the local model serving ecosystem (Ollama, llama.cpp bindings) are all Python-native. 3.11 specifically for the performance improvements (speedup over 3.10).

**Version pinning:** Python 3.11.x (not 3.12+) — some NLP libraries lag on 3.12 support as of v1.0.0.

**Alternatives rejected:**
- Node.js — weak NLP ecosystem; would require Python subprocess calls anyway
- Go — excellent for daemons, but the ML library situation is immature
- Rust — ideal for performance, but no mature ML ecosystem

---

### Web Framework: FastAPI 0.110+
**Why:** FastAPI is the correct choice for a local AI service daemon:
- Native async support (critical for non-blocking capture processing)
- Automatic OpenAPI docs (useful for debugging)
- Pydantic v2 request/response validation
- Native WebSocket support
- Trivially lightweight (~30MB RAM)

**Alternatives rejected:**
- Flask — synchronous by default, requires Gunicorn/async workaround
- Django — massive overkill; we don't need ORM, admin, or templating
- Starlette (raw) — FastAPI is Starlette with validation; no reason to go lower

---

### Agent Orchestration: LangGraph 0.1+
**Why:** LangGraph provides stateful, graph-based agent workflows with built-in checkpointing. It is used for the extraction pipeline orchestration — specifically the three-pass extraction state machine and the conflict resolution workflow.

**What LangGraph gives us:**
- State machines with persistent checkpoints
- Built-in retry logic
- Streaming support (useful for LLM extraction pass output)
- Integration with LangChain tool ecosystem

**Used for:**
- Extraction pipeline state machine (rule pass → NER pass → LLM pass → score → commit)
- Conflict resolution workflow
- Consolidation pipeline

**Alternatives rejected:**
- LangChain chains (non-graph) — no state persistence, linear only
- Prefect/Airflow — overkill, designed for batch data pipelines
- Custom state machine — we'd just be rewriting LangGraph

---

### NLP: spaCy 3.7+ (en_core_web_sm)
**Why:** spaCy is the industry standard for production NLP. The `en_core_web_sm` model is 12MB and runs in < 30ms for NER + dependency parsing on a typical conversation turn. The custom entity ruler extends it with tech-domain vocabulary.

**Pipeline used:**
- `ner` — named entity recognition (PERSON, ORG, PRODUCT, etc.)
- `parser` — dependency parsing for relationship extraction
- Custom `entity_ruler` — tech-domain entities (PostgreSQL, FastAPI, etc.)

**Installation:**
```bash
pip install spacy
python -m spacy download en_core_web_sm
```

**Alternatives rejected:**
- NLTK — older, slower, less accurate
- Stanford NLP — Java dependency (unacceptable)
- Hugging Face NER models — much larger (100MB+), slower; spaCy is sufficient for our use case

---

### Local LLM: Phi-4 Mini via Ollama
**Why:** The LLM extraction pass requires a model that can follow structured JSON output instructions reliably on consumer hardware.

**Phi-4 Mini selection rationale:**
- 3.8B parameters — runs on 8GB RAM without GPU
- Strong instruction following (benchmarks confirm structured output quality)
- MIT license — no usage restrictions
- Microsoft's model — well-maintained

**Serving via Ollama:**
```bash
ollama pull phi4-mini
ollama serve  # Runs on localhost:11434
```

**Ollama was chosen because:**
- Dead-simple model management
- Consistent REST API across models
- Handles GPU/CPU detection automatically
- No Python server process required (separate daemon)

**Fallback model hierarchy:**
1. Phi-4 Mini (local, default)
2. Qwen 2.5 3B (local, alternative)
3. Claude Haiku via API (remote fallback, user must enable)

**Alternatives rejected:**
- llama.cpp Python bindings — Ollama wraps this; cleaner API
- GPT4All — less reliable structured output
- Running Mistral 7B — too large for < 300MB RAM target during inference window

---

### Embeddings: sentence-transformers (BGE-M3)
**Why:** BGE-M3 from BAAI is the current state of the art for multilingual, multi-task dense retrieval. At 567MB, it's larger than we'd like, but the quality improvement over smaller models is significant for retrieval accuracy.

**Key properties:**
- 1024-dim embeddings (truncated to 384-dim for storage efficiency in our config)
- Runs fully on CPU (no GPU required)
- Inference: ~50ms per batch on M3 chip, ~150ms on Intel
- Multilingual support out of the box

**Alternative: nomic-embed-text-v1.5**
- 137MB (much smaller)
- 768-dim
- Slightly lower quality on technical text
- Recommended for users on machines with < 8GB RAM (configurable in settings)

**Alternatives rejected:**
- OpenAI text-embedding-3 — requires API calls, breaks local-first
- Cohere embed — same issue
- TF-IDF / BM25 only — insufficient for semantic similarity

---

### Vector Store: Qdrant (Local Mode)
**Why:** Qdrant is the best self-hosted vector database for our use case:
- Runs as an embedded library (no separate Docker container)
- Filtering support (filter by workspace_id, node_type, status) — critical for workspace isolation
- On-disk storage (no data loss on restart)
- Rust implementation — low memory overhead (~100MB per workspace at 10k vectors)
- Local mode is production-ready

**Installation:**
```python
pip install qdrant-client
# No external service needed — local mode uses file storage
from qdrant_client import QdrantClient
client = QdrantClient(path="~/.mnemosyne/workspaces/{id}/vectors/")
```

**Alternatives rejected:**
- Chroma — slower, less stable at scale, Python-native (higher memory)
- FAISS — no persistence, no filtering, Meta-maintained (slower updates)
- Pinecone — cloud-only, violates local-first requirement
- Weaviate — requires Docker, too heavy for local daemon
- LanceDB — promising but immature; revisit for v2

---

### Structured Storage: SQLite 3.45+ (with SQLCipher)
**Why:** See Document 03 for full rationale. Summary:
- Zero footprint (file-based)
- ACID compliant
- WAL mode prevents corruption on crash
- Recursive CTEs for graph traversal
- FTS5 for full-text search
- SQLCipher adds AES-256 encryption at rest

**SQLCipher installation:**
```bash
pip install sqlcipher3-wheels  # Pre-built wheels for Mac/Linux/Windows
```

**Configuration:**
```python
conn.execute("PRAGMA key='user_derived_key'")
conn.execute("PRAGMA cipher_page_size=4096")
conn.execute("PRAGMA kdf_iter=256000")  # PBKDF2 iterations
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

**Alternatives rejected:**
- PostgreSQL — requires a server process; violates local-first; overkill
- DuckDB — excellent for analytics but OLAP-oriented; graph traversal is worse
- Neo4j Community — JVM required (500MB+ RAM); unacceptable
- TinyDB — no SQL, no ACID, no FTS; too simple

---

### Task Queue: asyncio.Queue (In-Process)
**Why:** The capture queue doesn't need a separate broker. Python's asyncio.Queue provides a thread-safe, async-native queue that fits perfectly in the FastAPI event loop.

**For crash recovery:** The queue is checkpointed to disk (JSONL file) on every push. On startup, any unprocessed items are replayed.

**Alternatives rejected:**
- Redis — separate process dependency; overkill for single-user local daemon
- Celery — distributed task queue; massive overkill; adds Broker requirement
- RQ — Redis required

---

### Process Management: systemd (Linux) / launchd (macOS) / Windows Service
**Why:** The Mnemosyne daemon must start automatically at login and restart on crash. Each OS has a native facility for this.

**macOS plist:**
```xml
<!-- ~/Library/LaunchAgents/com.mnemosyne.plist -->
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ProgramArguments</key>
<array>
    <string>/usr/local/bin/mnemosyne-engine</string>
</array>
```

**Linux systemd unit:**
```ini
[Unit]
Description=Mnemosyne Memory Engine

[Service]
ExecStart=/usr/local/bin/mnemosyne-engine
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

**Alternatives rejected:**
- PM2 — Node.js process manager; wrong runtime
- Docker — adds container overhead; not suitable for user desktop daemon
- supervisord — works, but less native than systemd/launchd

---

## 4. SECURITY

### Encryption: SQLCipher (AES-256-CBC)
**Why:** Industry standard SQLite encryption. The key is derived from the machine hardware ID (default) or user password (opt-in) using PBKDF2-HMAC-SHA512.

### Token Generation: Python `secrets` module
```python
import secrets
TOKEN = secrets.token_urlsafe(32)  # 256-bit URL-safe token
```

### HTTPS: Self-signed cert on localhost
**Why:** Even on localhost, HTTPS prevents extension-to-engine traffic from being read by other local processes via port-sniffing. The self-signed cert is generated on install and pinned in the extension.

```python
# Generated on first run
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
# ... generates localhost cert valid for 10 years
```

---

## 5. DEVELOPMENT TOOLING

### Package Management: uv (Python) + pnpm (Node)
- `uv` — Rust-based Python package manager; 10-100x faster than pip
- `pnpm` — Disk-efficient Node package manager; hard links instead of copies

### Type Checking: mypy (Python) + TypeScript strict mode
- `mypy --strict` on all Python service code
- `"strict": true` in tsconfig.json for extension code

### Linting: ruff (Python) + ESLint + Prettier (TypeScript)
- `ruff` — replaces flake8, isort, and many mypy checks; extremely fast

### Testing: pytest (Python) + Vitest (TypeScript)
**See Document 15 (Testing Strategy) for full detail.**

### Database Migrations: custom migration runner
A simple sequential migration system — no Alembic (overkill for SQLite schema evolution):
```python
MIGRATIONS = [
    ("001_initial", create_initial_schema),
    ("002_add_embedding_id", add_embedding_column),
    ("003_add_health_score", add_health_score_column),
]
```

---

## 6. COMPLETE VERSION MANIFEST

| Component | Package | Version | License |
|-----------|---------|---------|---------|
| Extension Runtime | TypeScript | 5.4.x | Apache-2.0 |
| Extension Framework | Plasmo | 0.88.x | MIT |
| UI Framework | React | 18.3.x | MIT |
| Styling | Tailwind CSS | 3.4.x | MIT |
| State Mgmt | Zustand | 4.5.x | MIT |
| Graph Viz | Cytoscape.js | 3.29.x | MIT |
| Python Runtime | CPython | 3.11.x | PSF |
| Web Framework | FastAPI | 0.110.x | MIT |
| Validation | Pydantic | 2.6.x | MIT |
| Agent Framework | LangGraph | 0.1.x | MIT |
| NLP | spaCy | 3.7.x | MIT |
| NLP Model | en_core_web_sm | 3.7.x | MIT |
| LLM Serving | Ollama | 0.1.x | MIT |
| Default LLM | Phi-4 Mini | — | MIT |
| Embeddings | sentence-transformers | 2.7.x | Apache-2.0 |
| Embedding Model | BGE-M3 | — | MIT |
| Vector Store | qdrant-client | 1.8.x | Apache-2.0 |
| Structured DB | SQLite | 3.45+ | Public Domain |
| Encryption | SQLCipher | 4.5.x | BSD |
| Python Crypto | cryptography | 42.x | Apache-2.0 |
| HTTP Client | httpx | 0.27.x | BSD |
| Async | asyncio | stdlib | PSF |
| Package Mgr (Py) | uv | 0.1.x | Apache-2.0 |
| Package Mgr (JS) | pnpm | 9.x | MIT |
| Linter (Py) | ruff | 0.3.x | MIT |
| Type Check (Py) | mypy | 1.9.x | MIT |
| Test (Py) | pytest | 8.x | MIT |
| Test (JS) | Vitest | 1.x | MIT |

---

## 7. KNOWN RISKS AND MITIGATIONS

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Ollama not installed on user machine | High | LLM pass disabled | Graceful fallback to rule+NER only; display install prompt |
| BGE-M3 model too large for some machines | Medium | Slow first startup | Alternative: nomic-embed-text-v1.5 (137MB, configurable) |
| SQLCipher Python wheels broken on some platforms | Low | Storage unencrypted | Fallback to unencrypted SQLite with warning |
| spaCy model missing | Medium | NER pass skipped | Auto-download on first run; graceful degradation |
| Chrome MV3 restrictions on content scripts | Medium | Capture may break | Aggressive testing on all supported platforms per release |
| Qdrant local mode behavior change | Low | Vector search broken | Pin qdrant-client version strictly; integration test suite |
