# Project Mnemosyne — Implementation Plan Fix Index
## Maps every conflict/gap from CONFLICT_ANALYSIS.md to its fix file
---

All 15 issues (12 conflicts + 3 gaps) from the conflict analysis are addressed here.
Each fix file contains only the changed code — not the entire implementation plan.
Apply fixes in any order; they are independent of each other.

---

## Quick Reference Table

| Conflict ID | Plan | File(s) to change | Fix file |
|---|---|---|---|
| C-01 | 01 | `backend/db/schema.py` | `FIX_plan_01.md` |
| C-02 | 01 | `backend/db/encryption.py` | `FIX_plan_01.md` |
| C-03 | 02 | `backend/extraction/pipeline.py` | `FIX_plan_02.md` |
| C-14 | 03 | `backend/services/consolidation_service.py` | `FIX_plan_03.md` |
| C-04 | 04 | `backend/main.py`, `update_service.py`, `llm_extractor.py` | `FIX_plan_04.md` |
| C-15 | 04 | `backend/db/schema.py` (global.db index) | `FIX_plan_04.md` |
| C-05 | 05 | `backend/services/retrieval_service.py` | `FIX_plan_05.md` |
| C-06 | 06 | `extension/tailwind.config.js` | `FIX_plan_06.md` |
| C-07 | 07 | `extension/sidebar/index.tsx`, `extension/content/injector.ts` | `FIX_plan_07.md` |
| C-08 | 08 | `dashboard/app.tsx`, `dashboard/pages/ReviewPage.tsx` (new) | `FIX_plan_08.md` |
| C-09 | 10 | `tests/performance/test_latency.py`, `tests/conftest.py` | `FIX_plan_10.md` |
| C-10 | 11 | `backend/utils/logging.py` | `FIX_plan_11.md` |
| C-11 | 11 | `scripts/uninstall_linux.sh` (new file) | `FIX_plan_11.md` |
| C-12 | 12 | `conversation_threads` SQL schema (in graph.db) | `FIX_plan_12.md` |
| C-13 | 12 | `backend/services/snapshot_service.py` (comment guard) | `FIX_plan_12.md` |

---

## Issue Severity by Category

### Runtime Crashes (fix before any testing)
- **C-01** — `WorkspaceStatus.DELETED` causes SQLite CHECK violation on workspace delete
- **C-04** — `network_activity_logger` middleware crashes on `AttributeError: state.network_repo`

### Silent Wrong Behaviour (fix before benchmarking / QA)
- **C-05** — Decay formula ignores per-node `decay_rate`; all nodes decay identically
- **C-03** — LLM pass skipped for dense multi-topic turns; extraction recall drops
- **C-10** — Log rotation never triggers predictably; "7 days" retention guarantee broken

### Security / Correctness (fix before release)
- **C-02** — Missing SQLCipher KDF algorithm PRAGMA; possible weaker encryption on some builds
- **C-12** — Phantom FK constraint creates false referential integrity assumption

### Visual / UX Bugs (fix before UI review)
- **C-06** — Wrong success color (#22C55E vs #10B981); design system inconsistency
- **C-07** — Sidebar 20px too narrow; layout overflow in sidebar components
- **C-08** — Pending Review page unreachable from dashboard nav

### Missing Coverage (fix before CI is considered complete)
- **C-09** — 3 of 8 Doc 14 §6 performance targets have no benchmark tests
- **C-11** — No Linux uninstaller; Linux users have no removal path
- **C-14** — Magic number `0.92` instead of named constant `MERGE_THRESHOLD`
- **C-15** — `network_activity` table missing timestamp index; UC-22 queries are full scans
- **C-13** — Architectural guard missing from `SnapshotService` (future-proofing)

---

## Plans with no fixes needed
- Plan 00 — Clean
- Plan 09 — Clean (retrospective extraction correctly implemented per Doc 09 §9)
- Plans 06, 11 — Only the specific items listed above; all other content is correct

---

## How to apply

1. Open the original implementation plan file
2. Open the corresponding FIX file
3. Each fix shows exact **Find / Replace** blocks — locate the find-text in the original
   and substitute the replace-text
4. For new files (C-08 `ReviewPage.tsx`, C-11 `uninstall_linux.sh`), create the file
   at the path shown and paste the content from the fix file
5. Do not touch any code not referenced in a fix — the rest of each plan is correct
