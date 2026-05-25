# DOCUMENT 14 — DOS AND DON'TS
## Engineering Laws for Project Mnemosyne
**Project Mnemosyne**
**Version: 1.0.0**

---

> This document contains the non-negotiable engineering principles of Mnemosyne.
> Not guidelines. Not suggestions. Laws.
> Every decision made on this project should be cross-checked against this list.
> If a proposed change violates a law here, it does not ship. Period.

---

## SECTION 1: DATA LAWS

### ✅ DO: Extract structure from conversations
Every interaction with an AI platform should produce structured cognitive artifacts — goals, decisions, facts, entities. This is the core value proposition.

```python
# RIGHT
{
  "type": "decision",
  "content": "Switched to monocular depth estimation",
  "rationale": "Lower latency than SLAM",
  "created_at": "2025-06-05"
}
```

### ❌ DON'T: Store raw conversation text
Raw transcripts are never written to disk. Ever. Not even temporarily. Not even "just for debugging."

```python
# WRONG — never do this
db.execute("INSERT INTO conversations (text) VALUES (?)", [full_transcript])
```

**Why:** Raw transcripts accumulate sensitive data, grow unbounded, degrade retrieval quality, and create privacy liability. Every piece of useful information should instead live in a structured memory node.

---

### ✅ DO: Version every memory update
When a fact changes, archive the old version with `valid_until` set. Create the new version with `valid_from` set. Never overwrite.

```python
# RIGHT
old_node.valid_until = now()
old_node.status = SUPERSEDED
new_node = old_node.copy()
new_node.version += 1
new_node.content = updated_content
new_node.valid_from = now()
```

### ❌ DON'T: Overwrite memory nodes in place
`UPDATE memory_nodes SET content = ? WHERE id = ?` is illegal for content changes. This destroys history.

**Why:** Temporal versioning is what makes Mnemosyne trustworthy. "What did we decide on June 3?" must always be answerable. Overwriting destroys that capability.

---

### ✅ DO: Maintain the audit log for every state-changing operation
Every create, update, delete, conflict resolution, and workspace action must be recorded in the audit log.

### ❌ DON'T: Silently modify or delete memory
Any change to the knowledge graph that is invisible to the user is a bug, not a feature.

---

### ✅ DO: Apply the sensitive data filter before anything else
The sensitive data filter is the first thing in the capture pipeline. No other code runs before it.

### ❌ DON'T: Log message content anywhere
Not in debug logs. Not in error messages. Not in stack traces. Message content is private.

```python
# WRONG — logs user message content
logger.debug(f"Processing message: {capture.user_message}")

# RIGHT — log only metadata
logger.debug(f"Processing capture {capture.id}, platform={capture.platform}, length={len(capture.user_message)}")
```

---

## SECTION 2: ARCHITECTURE LAWS

### ✅ DO: Keep every operation workspace-scoped
Every query, every write, every retrieval must include a `workspace_id`. Global state is the enemy.

```python
# RIGHT
get_nodes(workspace_id=workspace_id, node_type=NodeType.GOAL)

# WRONG — retrieves across all workspaces
get_all_nodes(node_type=NodeType.GOAL)
```

### ❌ DON'T: Allow workspace memory to bleed into another workspace
Cross-workspace contamination is a critical bug. An entity in "Work Project A" has zero relationship to the same-named entity in "Work Project B" unless the user explicitly links them.

---

### ✅ DO: Make the local engine stateless per request
Each HTTP request to the FastAPI engine must be self-contained. No request-level global state.

### ❌ DON'T: Add network dependencies to the critical path
If the capture or retrieval flow requires an external network call, it will fail silently in airplane mode, on poor connections, or when services are down. Everything in the critical path must work offline.

**The only exception:** Cloud LLM fallback — explicitly user-enabled, clearly indicated to user, gracefully degraded when unavailable.

---

### ✅ DO: Design for crash recovery from the start
- SQLite WAL mode must always be on
- The capture queue must be disk-backed
- Engine startup must replay any unprocessed queue items

### ❌ DON'T: Assume the daemon will always be running
The extension must degrade gracefully when the engine is offline. It must never block the user's AI interaction because Mnemosyne is down.

---

### ✅ DO: Use async everywhere in the engine
FastAPI + asyncio enables non-blocking I/O. All database operations, embedding generation, and extraction passes must be async-compatible.

### ❌ DON'T: Block the event loop with synchronous I/O
```python
# WRONG — blocks event loop
result = run_extraction(text)  # Synchronous

# RIGHT — non-blocking
result = await run_extraction(text)  # Async
```

---

## SECTION 3: EXTRACTION LAWS

### ✅ DO: Set confidence thresholds conservatively
When in doubt, queue for review. False positives in memory are worse than false negatives.

```python
AUTO_COMMIT_THRESHOLD = 0.80   # Only commit things we're very confident about
MIN_CONFIDENCE = 0.60           # Below this, discard entirely
REVIEW_THRESHOLD = 0.60         # Between MIN and AUTO_COMMIT goes to user review
```

### ❌ DON'T: Extract from hypothetical statements
"What if we used MongoDB?" should never create a TECHNICAL_FACT node for MongoDB. The extraction engine must distinguish between "what is" and "what if".

**Detection heuristic:**
```python
HYPOTHETICAL_MARKERS = [
    "what if", "imagine if", "suppose we", "could we", "we might",
    "one option is", "alternatively", "we could consider", "theoretically",
    "just brainstorming"
]
```

---

### ✅ DO: Allow users to correct any extraction
Every extraction visible in the audit UI must be editable and deletable, no exceptions.

### ❌ DON'T: Auto-commit user-verified nodes into conflicts
If a node was manually verified by the user (`user_verified = true`), it must go through user review before being superseded. The system's auto-resolution cannot override human judgment.

---

### ✅ DO: Gracefully degrade when the LLM is unavailable
Rule-based + NER extraction is always available and provides useful output. LLM extraction is additive.

### ❌ DON'T: Fail silently when extraction produces no candidates
If a conversation turn produces zero extractions, that is a valid outcome. Log it at DEBUG level. Don't try to force-produce extractions.

---

## SECTION 4: RETRIEVAL LAWS

### ✅ DO: Include goals and decisions in every context injection
Active goals and recent decisions are always relevant, regardless of semantic similarity to the current query.

### ❌ DON'T: Return conflicting nodes in the same retrieval result
The conflict resolution system must catch and exclude contradictory nodes before they reach the context builder. Serving both sides of a contradiction to the AI is worse than serving neither.

---

### ✅ DO: Respect the token budget strictly
The context string must never exceed `token_budget`. If trimming is required, trim the lowest-ranked nodes first.

### ❌ DON'T: Stuff the context with low-quality nodes to fill the budget
Quality over quantity. 8 high-relevance nodes beat 40 marginally-relevant ones.

---

### ✅ DO: Update `last_accessed` timestamps on every retrieval
Retrieval is a reinforcement signal. Nodes that get retrieved stay relevant longer.

### ❌ DON'T: Sort retrieval results by creation date
Creation date is a terrible proxy for relevance. Always use the compound retention score (importance × recency × reinforcement × workspace_relevance).

---

## SECTION 5: UI LAWS

### ✅ DO: Make the injection indicator always visible
The user must always be able to see whether context was injected, and what was injected. Trust requires transparency.

### ❌ DON'T: Inject context invisibly without user knowledge
Silent background behavior destroys trust. Every action Mnemosyne takes on the user's behalf must be visible.

---

### ✅ DO: Make disable/pause always one click away
Capture toggle. Injection disable. These must be accessible from the extension icon — never buried in settings.

### ❌ DON'T: Create any modal dialogs that interrupt AI interaction
Mnemosyne runs alongside AI platforms. We must never disrupt the user's flow. Notifications are badges and banners, never blocking modals.

---

### ✅ DO: Load the sidebar in < 500ms
The sidebar is the primary UI. Any load time > 500ms feels broken.

### ❌ DON'T: Show spinners for operations that should be instant
Data that exists locally should appear instantly. If it takes > 200ms to show memory nodes from local SQLite, that is a performance bug to fix, not a UX pattern to design around.

---

## SECTION 6: PERFORMANCE LAWS

| Operation | Target | Hard Limit |
|-----------|--------|-----------|
| Context injection (retrieval) | < 300ms | 500ms |
| Extraction pipeline (per turn) | < 500ms | 1500ms |
| Sidebar load | < 300ms | 500ms |
| Graph query (5-hop) | < 50ms | 200ms |
| Workspace switch | < 100ms | 300ms |
| Sensitive data filter | < 10ms | 30ms |
| Full-text search | < 100ms | 300ms |
| Engine RAM usage (at rest) | < 150MB | 300MB |

### ✅ DO: Benchmark these on every release
Performance regressions are bugs. Add benchmarks to the CI pipeline.

### ❌ DON'T: Add synchronous embedding generation to the retrieval path
Embedding generation (50-150ms per text) must happen asynchronously at commit time, not at retrieval time. Embeddings are always pre-computed.

---

## SECTION 7: TESTING LAWS

### ✅ DO: Test extraction accuracy on real conversation samples
The extraction benchmark suite must cover all personas and node types. Accuracy must be verified on each release.

### ❌ DON'T: Use production user data in tests
All test data must be synthetic. Never use real conversation content in the test suite.

---

### ✅ DO: Write integration tests for every conflict resolution strategy
Conflict resolution is the hardest logic in the system. Every strategy (temporal, preference merge, user review, logical flag) must have dedicated tests.

### ❌ DON'T: Ship conflict resolution changes without running the full test suite
Bugs in conflict resolution corrupt the knowledge graph silently. This is the highest-risk component.

---

## SECTION 8: THE PRIME DIRECTIVES

These supersede everything else:

1. **Never lose user data** — write-ahead logging, atomic commits, crash recovery. Data corruption is the worst possible outcome.

2. **Never send user data externally by default** — local-first is the identity of this product. Violating it breaks the fundamental trust contract.

3. **Never block the user's AI interaction** — if Mnemosyne is down, broken, or slow, the user's Claude/ChatGPT experience must continue unaffected.

4. **Never extract what isn't there** — false positives (things that aren't true) corrupt the knowledge graph and break AI context. When uncertain: queue for review, don't commit.

5. **Never hide what Mnemosyne is doing** — every action is visible in the audit log and the UI. Transparency is non-negotiable.
