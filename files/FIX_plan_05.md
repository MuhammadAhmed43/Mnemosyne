# FIX — Plan 05: Retrieval Service & Context Reconstruction
## Fix for C-05
---

## HOW TO USE THIS FILE
One line change inside one function. Surgical — nothing else touches.

---

## FIX C-05 — Decay formula uses hardcoded `0.1` instead of `node.decay_rate`
**File to edit:** `backend/services/retrieval_service.py`
**Function:** `_to_context_node(self, node, source, weight)`

**Find:**

```python
        days_since = (datetime.utcnow() - node.last_accessed).total_seconds() / 86400
        recency = math.exp(-0.1 * days_since)  # Recency factor
```

**Replace with:**

```python
        days_since = (datetime.utcnow() - node.last_accessed).total_seconds() / 86400
        # Use per-node decay_rate, NOT a hardcoded constant. (Doc 04 §8)
        # Each node type has its own decay rate set at creation time:
        #   PREFERENCE       → 0.005  (slow decay — stable patterns)
        #   TECHNICAL_FACT   → 0.01   (moderate — stack changes infrequently)
        #   GOAL / DECISION  → 0.02
        #   EVENT            → 0.08   (fast decay — events lose relevance quickly)
        # Using 0.1 for all types collapses this differentiation entirely.
        recency = math.exp(-node.decay_rate * days_since)  # Doc 04 §8 formula
```

**Why:** Doc 04 §8 defines the decay formula as:
`recency_factor = exp(-decay_rate × days_since_last_access)`
where `decay_rate` is a *per-node* property set at extraction time based on node type.
The plan hardcodes `0.1` — the same decay rate as an EVENT node — for every node type.
This means PREFERENCE nodes (which should stay relevant for months) decay as fast as
EVENT nodes (which should fade within two weeks). The compound retention score used for
ranking is broken without this fix, leading to wrong retrieval ordering.
(Ref: Doc 04 §8, C-05 conflict report)

---

## No other changes needed in Plan 05.
