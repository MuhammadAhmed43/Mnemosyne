# FIX — Plan 03: Graph Store, Retrieval & Consolidation
## Fix for C-14
---

## HOW TO USE THIS FILE
One line to add at the top of one file. Surgical — do not touch anything else.

---

## FIX C-14 — `MERGE_THRESHOLD` used as magic number instead of named constant
**File to edit:** `backend/services/consolidation_service.py`
**Location:** Top of the file, after imports, before any class definitions

**Find the imports block (wherever it ends) and add the following constant immediately after:**

```python
# ── Consolidation constants (Doc 10 §5) ──────────────────────────────────────
# Cosine similarity threshold above which two nodes are considered near-duplicates
# and eligible for merging during the nightly consolidation pass.
# Value sourced from Doc 10 §5. Change requires benchmark re-validation.
MERGE_THRESHOLD: float = 0.92
```

**Then find the magic number in `_merge_similar()`:**

```python
            similar = await self.embeddings.find_similar(
                workspace_id, node.embedding_id, top_k=3, threshold=0.92)
```

**Replace `0.92` with the named constant:**

```python
            similar = await self.embeddings.find_similar(
                workspace_id, node.embedding_id, top_k=3, threshold=MERGE_THRESHOLD)
```

**Why:** Doc 10 §5 defines `MERGE_THRESHOLD = 0.92` as a named project constant. Plan 03
uses the correct value but inlines it as a magic number directly in the `find_similar()`
call. This means if the threshold ever needs tuning (e.g. after a model change), a developer
has to hunt through function bodies instead of changing one constant at the top of the file.
Doc 14 §3 pattern requires thresholds to be named constants. This fix is pure refactor —
no behaviour change. (Ref: Doc 10 §5, Doc 14 §3, C-14 conflict report)

---

## No other changes needed in Plan 03.
