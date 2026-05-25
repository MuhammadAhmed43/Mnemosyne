# Project Mnemosyne — Implementation Plan Conflict Analysis
## Full audit of Plans 00–12 against Requirements Docs 01–17
**Status: 12 CONFLICTS + 3 GAPS found and fixed**

---

## Summary Table

| # | Plan | Type | Description | Req. Doc |
|---|------|------|-------------|----------|
| C-01 | 01 | CONFLICT | `WorkspaceStatus.DELETED` in Python enum but NOT in `workspaces` SQL CHECK | Doc 07 §3.1 |
| C-02 | 01 | CONFLICT | `configure_sqlcipher()` missing `PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512` | Doc 13 §3.1 |
| C-03 | 02 | CONFLICT | `_should_run_llm_pass()` missing 4th trigger: multi-topic complexity check | Doc 06 §5.1 |
| C-04 | 04 | CONFLICT | `network_activity_logger` middleware references undefined `state.network_repo`; logs incoming requests (wrong direction) | Doc 13 §6 |
| C-05 | 05 | CONFLICT | Decay formula in `_to_context_node` uses hardcoded `0.1` decay exponent — must use `node.decay_rate` per formula | Doc 04 §8 |
| C-06 | 06 | CONFLICT | Tailwind `success: '#22C55E'` — should be `#10B981` | Doc 09 §2.1 |
| C-07 | 07 | CONFLICT | Sidebar described as "360px wide" — must be 380px (default) | Doc 09 §9 |
| C-08 | 08 | CONFLICT | Dashboard nav missing "Review" (Pending Review) route | Doc 09 §6 |
| C-09 | 10 | CONFLICT | `test_latency.py` benchmarks cover only 5 of 8 required operations from the performance law table | Doc 14 §6 |
| C-10 | 11 | CONFLICT | Log rotation uses `RotatingFileHandler` (size-based); must be daily (`TimedRotatingFileHandler`) | Doc 16 §5.1 |
| C-11 | 11 | GAP | `scripts/uninstall_linux.sh` missing entirely | Doc 16 §8 |
| C-12 | 12 | CONFLICT | `conversation_threads` SQL has `REFERENCES workspaces(id)` — cross-database FK impossible in SQLite | Doc 07 (arch) |
| C-13 | 12 | GAP | `workspace_snapshots` table (Memory Snapshots feature) placed in global.db but snapshots are workspace-scoped data | Plan 12 §3 |
| C-14 | 03 | GAP | `MERGE_THRESHOLD` constant for consolidation not defined as a named constant (magic number risk) | Doc 10 §5 |
| C-15 | 04 | GAP | `network_activity` table in global.db has no index on `timestamp` — privacy audit queries will be slow | Doc 12 UC-22 |

---

## Detailed Analysis & Fixes

---

### C-01 — Plan 01: `WorkspaceStatus.DELETED` not in SQL CHECK
**File:** `backend/db/schema.py` — global.db `workspaces` table  
**Problem:** The Python enum has `DELETED = "deleted"` but the SQL constraint only allows `('active', 'archived', 'paused')`. Any code that sets `status='deleted'` causes a CHECK constraint violation (runtime crash).  
**Fix in Plan 01:** Add `'deleted'` to the `CONSTRAINT valid_status CHECK` in the `workspaces` table. See fixed Plan 01, §4.1.

---

### C-02 — Plan 01: `configure_sqlcipher()` missing KDF algorithm PRAGMA
**File:** `backend/db/encryption.py`  
**Problem:** Doc 13 §3.1 specifies `conn.execute("PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512")` must be set. Plan 01 only sets `kdf_iter` and `cipher_hmac_algorithm`. Without `cipher_kdf_algorithm`, SQLCipher may default to a weaker KDF on some versions.  
**Fix in Plan 01:** Add the missing PRAGMA to `configure_sqlcipher()`. See fixed Plan 01, §6.

---

### C-03 — Plan 02: `_should_run_llm_pass()` missing 4th trigger condition
**File:** `backend/extraction/pipeline.py`  
**Problem:** Doc 06 §5.1 lists 4 conditions that trigger the LLM pass. Plan 02 implements 3 of them but omits condition 4: *"Text discusses multiple complex topics."* This causes the LLM pass to be skipped for short multi-topic conversations (e.g., touching goals, tech stack, AND decisions in one message), reducing extraction recall.  
**Fix in Plan 02:** Add a multi-entity/topic complexity check in `_should_run_llm_pass()`. See fixed Plan 02, §8.

---

### C-04 — Plan 04: Broken `network_activity_logger` middleware
**File:** `backend/main.py`  
**Problem:** The middleware calls `await state.network_repo.log(...)` but `network_repo` is never initialized in `app.state`. It also captures *incoming* requests to the FastAPI server, not *outgoing* requests from the engine (to Ollama, GitHub, etc.). The if-condition `not request.url.path.startswith("/api")` means it would try to log health and WS endpoint calls — all using the undefined `state` reference.  
**Fix in Plan 04:** Remove the broken middleware. Network activity logging for outbound calls (update checks, cloud LLM fallback) must be added at the call site in `UpdateService.check_for_updates()` and `LLMExtractor` (cloud fallback path). See fixed Plan 04, §1.

---

### C-05 — Plan 05: Decay formula uses hardcoded `0.1` instead of `node.decay_rate`
**File:** `backend/services/retrieval_service.py` — `_to_context_node()`  
**Problem:** Doc 04 §8 defines:  
`recency_factor = exp(-decay_rate × days_since_last_access)`  
Plan 05 uses `math.exp(-0.1 * days_since)` — a hardcoded value that ignores each node's individual `decay_rate`. This means all node types decay at the same rate during scoring, breaking the differentiated retention system (e.g., PREFERENCE nodes should decay at 0.005, TECHNICAL_FACT at 0.01, EVENT at 0.08).  
**Fix in Plan 05:** Replace `0.1` with `node.decay_rate`. See fixed Plan 05, §2.

---

### C-06 — Plan 06: Wrong success color in Tailwind config
**File:** `extension/tailwind.config.js`  
**Problem:** `success: '#22C55E'` (Tailwind green-500). Doc 09 §2.1 specifies `--color-success: #10B981` (Tailwind emerald-500). These are visually distinct. All success states (completed goals, confirmed extractions) will render in the wrong green shade, inconsistent with the design system.  
**Fix in Plan 06:** Change `success: '#22C55E'` → `success: '#10B981'`. See fixed Plan 06, §1.

---

### C-07 — Plan 07: Sidebar width 360px vs required 380px
**File:** `extension/sidebar/index.tsx` and `extension/content/injector.ts`  
**Problem:** Plan 07 header comment says "360px wide" and the injector likely uses this value. Doc 09 §9 specifies: "Default: 380px". This affects the rendered sidebar width, conflicts with the design system, and will cause layout issues in the sidebar components designed for 380px.  
**Fix in Plan 07:** Update all sidebar width references from 360px → 380px. See fixed Plan 07, §1.

---

### C-08 — Plan 08: Dashboard missing "Review" (Pending Review) page
**File:** `dashboard/app.tsx` — `NAV_ITEMS`  
**Problem:** Doc 09 §6 explicitly shows the full audit page sidebar with these nav items: Overview, Graph, Memory, **Review**, Timeline, Conflicts, Settings. Plan 08 has all except "Review". This means the pending review workflow (approve/reject extractions) is inaccessible from the dashboard tab page — users can only access it from the sidebar.  
**Fix in Plan 08:** Add `{ path: '/review', label: 'Review', icon: '⚠️' }` to `NAV_ITEMS` and add the corresponding `<Route>` and `ReviewPage` component. See fixed Plan 08, §1.

---

### C-09 — Plan 10: Performance benchmarks miss 3 of 8 required operations
**File:** `tests/performance/test_latency.py`  
**Problem:** Doc 14 §6 defines performance targets for 8 operations. Plan 10 tests context injection, extraction, graph query, and sidebar load. Missing: workspace switch (<100ms), sensitive data filter (<10ms), full-text search (<100ms), and engine RAM at rest (<300MB).  
**Fix in Plan 10:** Add the missing 3 latency tests and a RAM usage test. See fixed Plan 10, §3.

---

### C-10 — Plan 11: Log rotation is size-based, not daily
**File:** `backend/utils/logging.py`  
**Problem:** Doc 16 §5.1 says *"rotated daily, keep 7 days."* Plan 11 uses `RotatingFileHandler(maxBytes=10_000_000)` which is *size-based*, not date-based. This means logs could rotate multiple times per day on a busy system or never rotate on a quiet system, making the "keep 7 days" behavior unpredictable.  
**Fix in Plan 11:** Replace `RotatingFileHandler` with `TimedRotatingFileHandler(when='midnight', backupCount=7)`. See fixed Plan 11, §6.

---

### C-11 — Plan 11: Missing `uninstall_linux.sh`
**File:** `scripts/uninstall_linux.sh` — file not defined  
**Problem:** Doc 16 §8 documents uninstall procedures for all 3 platforms. Plan 11 includes `uninstall_windows.ps1` and `uninstall_macos.sh` but has no Linux uninstaller. The files summary and implementation section both omit it.  
**Fix in Plan 11:** Add `scripts/uninstall_linux.sh` to both the implementation and files summary. See fixed Plan 11, §10.

---

### C-12 — Plan 12: Cross-database `REFERENCES` in `conversation_threads`
**File:** Plan 12 §1, `conversation_threads` SQL schema  
**Problem:** `workspace_id TEXT NOT NULL REFERENCES workspaces(id)` — `conversation_threads` lives in `graph.db` (per-workspace), while `workspaces` lives in `global.db`. SQLite cannot enforce foreign keys across separate database files. Even with `PRAGMA foreign_keys=ON`, this constraint is silently ignored and creates conceptual confusion for developers who may assume it's enforced.  
**Fix in Plan 12:** Remove the `REFERENCES workspaces(id)` clause. Add a comment explaining that workspace existence is enforced at the application layer. See fixed Plan 12, §1.

---

### C-13 — Plan 12: `workspace_snapshots` stored in global.db (wrong database)
**File:** Plan 12 §3 (Memory Snapshots feature)  
**Problem:** Memory snapshots are per-workspace data (they snapshot nodes from a specific workspace). Placing them in global.db violates the workspace-scoped storage architecture (Doc 03 §6, Doc 14 §2). They should live in `graph.db` alongside the nodes they snapshot.  
**Fix in Plan 12:** Move `workspace_snapshots` table to the per-workspace `graph.db` schema. See fixed Plan 12, §3.

---

### C-14 — Plan 03: `MERGE_THRESHOLD` used as magic number
**File:** `backend/services/consolidation_service.py`  
**Problem:** Doc 10 §5 defines `MERGE_THRESHOLD = 0.92` as a named constant. Plan 03's consolidation service references this value but it's defined only inline. Not a runtime error, but violates the engineering law that thresholds be configurable named constants (Doc 14 §3 pattern).  
**Fix in Plan 03:** Define `MERGE_THRESHOLD: float = 0.92` at module level with a comment referencing Doc 10 §5. See fixed Plan 03, §5.

---

### C-15 — Plan 04: `network_activity` table missing timestamp index
**File:** `backend/db/schema.py` — global.db  
**Problem:** The `network_activity` table (added for UC-22 privacy audit) has no index on `timestamp`. The privacy audit view queries this table ordered by time. Without an index, this becomes a full table scan.  
**Fix in Plan 04:** Add `CREATE INDEX idx_network_ts ON network_activity(timestamp DESC);` after the table creation. See fixed Plan 04, §1 schema note.

---

## Files Changed Per Plan

| Plan | Files with Changes |
|------|--------------------|
| 01 | `backend/db/schema.py`, `backend/db/encryption.py` |
| 02 | `backend/extraction/pipeline.py` |
| 03 | `backend/services/consolidation_service.py` |
| 04 | `backend/main.py`, `backend/db/schema.py` (index) |
| 05 | `backend/services/retrieval_service.py` |
| 06 | `extension/tailwind.config.js` |
| 07 | `extension/sidebar/index.tsx`, `extension/content/injector.ts` |
| 08 | `dashboard/app.tsx`, `dashboard/pages/ReviewPage.tsx` (new) |
| 10 | `tests/performance/test_latency.py` |
| 11 | `backend/utils/logging.py`, `scripts/uninstall_linux.sh` (new) |
| 12 | Plan 12 §1 SQL schema, Plan 12 §3 SQL schema |

Plans **00, 06 (partial), 09** have no conflicts. Plan 00 is clean. Plan 09 correctly implements retrospective extraction (§9). Plan 06 needs only the color fix.
