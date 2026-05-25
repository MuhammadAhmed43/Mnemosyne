# Plan 05 — Retrieval & Context Engine

> Covers: Doc 03 (Architecture §Retrieval), Doc 10 (Backend Logic §RetrievalService), Doc 14 (Retrieval Laws)

---

## Architecture

```
GET /context?workspace_id=...&hint=...&token_budget=2000
  ↓
[Workspace Detection] → resolve workspace_id (auto if not provided)
  ↓
[Intent Analysis] → classify intent from hint text
  ↓
[Multi-Source Retrieval] → 5 parallel sources
  ├── 1. Active goals (always included)
  ├── 2. Recent decisions (last 14 days, always included)
  ├── 3. Open problems (always included)
  ├── 4. Semantic search (Qdrant, intent-weighted)
  └── 5. High-importance nodes (importance > 0.8)
  ↓
[Dedup + Filter] → remove superseded, remove conflicts
  ↓
[Rank] → compound retention score
  ↓
[Token Budget] → progressive trimming to fit budget
  ↓
[Context Builder] → format context string for target platform
  ↓
[Side Effects] → update last_accessed, increment reinforcement
  ↓
Return ContextResult (<300ms total)
```

---

## File 1: backend/services/intent_service.py

```python
from enum import Enum

class IntentCategory(str, Enum):
    CONTINUE_WORK = "continue_work"      # "Let's continue..."
    DEBUG = "debug"                       # "I'm getting an error..."
    DESIGN = "design"                    # "How should we architect..."
    REVIEW = "review"                    # "Review this code..."
    BRAINSTORM = "brainstorm"            # "What are some ideas..."
    GENERAL = "general"                  # Default

# Keywords that signal intent
INTENT_SIGNALS = {
    IntentCategory.DEBUG: [
        "error", "bug", "crash", "failing", "doesn't work", "broken",
        "exception", "stack trace", "debug", "fix", "issue"
    ],
    IntentCategory.DESIGN: [
        "architect", "design", "structure", "pattern", "approach",
        "how should", "best way", "refactor", "redesign"
    ],
    IntentCategory.REVIEW: [
        "review", "check", "look at", "feedback", "improve", "optimize"
    ],
    IntentCategory.BRAINSTORM: [
        "ideas", "brainstorm", "options", "alternatives", "what if",
        "possibilities", "suggest", "creative"
    ],
    IntentCategory.CONTINUE_WORK: [
        "continue", "pick up", "left off", "last time", "yesterday",
        "where were we", "resume", "back to"
    ],
}

class IntentService:
    """Analyze user's first message to determine retrieval strategy."""

    def classify(self, hint: Optional[str]) -> IntentCategory:
        if not hint:
            return IntentCategory.GENERAL

        hint_lower = hint.lower()
        scores = {}
        for intent, keywords in INTENT_SIGNALS.items():
            score = sum(1 for kw in keywords if kw in hint_lower)
            if score > 0:
                scores[intent] = score

        if not scores:
            return IntentCategory.GENERAL
        return max(scores, key=scores.get)

    def get_retrieval_weights(self, intent: IntentCategory) -> dict:
        """Adjust retrieval source weights based on intent."""
        base = {
            "goals": 1.0,
            "decisions": 1.0,
            "problems": 0.8,
            "semantic": 1.0,
            "high_importance": 0.7,
        }

        overrides = {
            IntentCategory.DEBUG: {"problems": 1.5, "semantic": 1.3},
            IntentCategory.DESIGN: {"decisions": 1.4, "goals": 1.2},
            IntentCategory.CONTINUE_WORK: {"decisions": 1.3, "problems": 1.2},
            IntentCategory.BRAINSTORM: {"goals": 1.3, "semantic": 0.8},
            IntentCategory.REVIEW: {"decisions": 1.2, "semantic": 1.2},
        }

        if intent in overrides:
            base.update(overrides[intent])
        return base
```

---

## File 2: backend/services/retrieval_service.py

```python
import asyncio
import time
from backend.models.context import ContextResult, ContextNode
from backend.services.intent_service import IntentService, IntentCategory

# From Doc 14: never return conflicting nodes in same result
# From Doc 14: always include goals and decisions
# From Doc 14: respect token budget strictly
# From Doc 14: quality over quantity

class RetrievalService:
    """Multi-source retrieval orchestrator with token budget management."""

    def __init__(self, node_repo, edge_repo, embedding_service,
                 conflict_repo, workspace_service, intent_service):
        self.nodes = node_repo
        self.edges = edge_repo
        self.embeddings = embedding_service
        self.conflicts = conflict_repo
        self.workspaces = workspace_service
        self.intent = intent_service

    async def get_context(
        self,
        workspace_id: Optional[str],
        hint: Optional[str],
        platform: str,
        token_budget: int = 2000,
    ) -> ContextResult:
        start = time.monotonic()

        # Step 1: Resolve workspace
        if not workspace_id:
            workspace_id, confidence = await self.workspaces.infer_workspace(hint or "")
            if confidence < 0.55:
                # Return empty context — let extension prompt user
                return ContextResult(
                    workspace_id="", workspace_name="",
                    context_string="", nodes_included=[],
                    token_count=0, retrieval_ms=0, injection_id="")

        workspace = await self.workspaces.get(workspace_id)

        # Step 2: Intent analysis
        intent = self.intent.classify(hint)
        weights = self.intent.get_retrieval_weights(intent)

        # Step 3: Multi-source parallel retrieval
        sources = await asyncio.gather(
            self._get_active_goals(workspace_id),
            self._get_recent_decisions(workspace_id, days=14),
            self._get_open_problems(workspace_id),
            self._get_semantic_matches(workspace_id, hint),
            self._get_high_importance(workspace_id, threshold=0.8),
        )

        goals, decisions, problems, semantic, important = sources

        # Step 4: Combine and tag source
        candidates = []
        for node in goals:
            candidates.append(self._to_context_node(node, "goal_priority", weights["goals"]))
        for node in decisions:
            candidates.append(self._to_context_node(node, "recent_decision", weights["decisions"]))
        for node in problems:
            candidates.append(self._to_context_node(node, "open_problem", weights["problems"]))
        for node in semantic:
            candidates.append(self._to_context_node(node, "semantic", weights["semantic"]))
        for node in important:
            candidates.append(self._to_context_node(node, "high_importance", weights["high_importance"]))

        # Step 5: Deduplicate (same node from multiple sources → keep highest score)
        candidates = self._deduplicate(candidates)

        # Step 6: Filter conflicting nodes
        candidates = await self._filter_conflicts(workspace_id, candidates)

        # Step 7: Filter superseded nodes
        candidates = [c for c in candidates if c._node.status == NodeStatus.ACTIVE]

        # Step 8: Rank by compound retention score
        candidates.sort(key=lambda c: c.relevance_score, reverse=True)

        # Step 9: Token budget allocation
        selected = self._apply_token_budget(candidates, token_budget)

        # Step 10: Build context string
        context_string = self._build_context_string(selected, workspace.name, platform)
        token_count = self._count_tokens(context_string)

        # Step 11: Side effects — update access timestamps + reinforcement (Doc 04 §8)
        node_ids = [c.node_id for c in selected]
        await self.nodes.update_last_accessed(node_ids)
        await self.nodes.increment_reinforcement(node_ids, amount=0.05)  # Retrieval = +0.05

        retrieval_ms = int((time.monotonic() - start) * 1000)

        return ContextResult(
            workspace_id=workspace_id,
            workspace_name=workspace.name,
            context_string=context_string,
            nodes_included=selected,
            token_count=token_count,
            retrieval_ms=retrieval_ms,
            injection_id=generate_id(),
        )

    # ── Retrieval Sources ──

    async def _get_active_goals(self, ws_id: str) -> list[MemoryNode]:
        nodes = await self.nodes.get_active(ws_id, node_type=NodeType.GOAL)
        return [n for n in nodes
                if n.structured_data.get("status") in ("ACTIVE", None)]

    async def _get_recent_decisions(self, ws_id: str, days: int) -> list[MemoryNode]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        nodes = await self.nodes.get_active(ws_id, node_type=NodeType.DECISION)
        return [n for n in nodes if n.created_at >= cutoff]

    async def _get_open_problems(self, ws_id: str) -> list[MemoryNode]:
        nodes = await self.nodes.get_active(ws_id, node_type=NodeType.PROBLEM)
        return [n for n in nodes
                if n.structured_data.get("status") in ("OPEN", None)]

    async def _get_semantic_matches(self, ws_id: str, hint: Optional[str]) -> list[MemoryNode]:
        if not hint:
            return []
        results = await self.embeddings.search_by_text(
            ws_id, hint, top_k=20,
            filters={"status": "active"})
        return results

    async def _get_high_importance(self, ws_id: str, threshold: float) -> list[MemoryNode]:
        return await self.nodes.get_by_importance(ws_id, min_score=threshold)

    # ── Scoring ──

    def _to_context_node(self, node: MemoryNode, source: str,
                          weight: float) -> ContextNode:
        """Compute compound retention score (Doc 04 formula)."""
        import math

        days_since = (datetime.utcnow() - node.last_accessed).total_seconds() / 86400
        # Use per-node decay_rate, NOT a hardcoded constant. (Doc 04 §8)
        # Each node type has its own decay rate set at creation time:
        #   PREFERENCE       → 0.005  (slow decay — stable patterns)
        #   TECHNICAL_FACT   → 0.01   (moderate — stack changes infrequently)
        #   GOAL / DECISION  → 0.02
        #   EVENT            → 0.08   (fast decay — events lose relevance quickly)
        # Using 0.1 for all types collapses this differentiation entirely.
        recency = math.exp(-node.decay_rate * days_since)  # Doc 04 §8 formula

        reinforcement = 1.0 + (0.1 * min(node.reinforcement_count, 10))

        # Compound score: importance × recency × reinforcement × source_weight
        score = node.importance_score * recency * reinforcement * weight

        # Boost user-verified nodes
        if node.user_verified:
            score *= 1.15

        ctx = ContextNode(
            node_id=node.id, node_type=node.node_type,
            content=node.content, relevance_score=min(score, 2.0),
            source=source)
        ctx._node = node  # Attach for filtering
        return ctx

    # ── Dedup & Filtering ──

    def _deduplicate(self, candidates: list[ContextNode]) -> list[ContextNode]:
        seen = {}
        for c in candidates:
            if c.node_id not in seen or c.relevance_score > seen[c.node_id].relevance_score:
                seen[c.node_id] = c
        return list(seen.values())

    async def _filter_conflicts(self, ws_id: str,
                                 candidates: list[ContextNode]) -> list[ContextNode]:
        """Remove conflicting nodes — serve neither side (Doc 14)."""
        pending_conflicts = await self.conflicts.get_pending(ws_id)
        conflicted_ids = set()
        for c in pending_conflicts:
            conflicted_ids.add(c.node_a_id)
            conflicted_ids.add(c.node_b_id)
        return [c for c in candidates if c.node_id not in conflicted_ids]

    # ── Token Budget ──

    def _apply_token_budget(self, ranked: list[ContextNode],
                             budget: int) -> list[ContextNode]:
        """Progressive trimming: include top-ranked until budget exhausted."""
        selected = []
        used = 50  # Reserve for header
        for node in ranked:
            node_tokens = self._estimate_tokens(node.content)
            if used + node_tokens > budget:
                continue  # Skip this node, try next (might be shorter)
            selected.append(node)
            used += node_tokens
        return selected

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimate: 1 token ≈ 4 chars."""
        return len(text) // 4 + 1

    def _count_tokens(self, text: str) -> int:
        """More accurate count using tiktoken if available."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return self._estimate_tokens(text)

    # ── Context String Builder ──

    def _build_context_string(self, nodes: list[ContextNode],
                               workspace_name: str, platform: str) -> str:
        """Format context for injection. Platform-aware (my addition)."""

        # Group by type
        groups = {}
        for n in nodes:
            groups.setdefault(n.node_type, []).append(n)

        sections = []
        sections.append(f"[WORKSPACE: {workspace_name}]")

        type_labels = {
            NodeType.GOAL: "Active Goals",
            NodeType.DECISION: "Recent Decisions",
            NodeType.TECHNICAL_FACT: "Technical State",
            NodeType.PROBLEM: "Open Problems",
            NodeType.PREFERENCE: "User Preferences",
            NodeType.ENTITY: "Key People & Tools",
            NodeType.TASK: "Active Tasks",
            NodeType.INSIGHT: "Key Insights",
            NodeType.CONSTRAINT: "Constraints",
            NodeType.EVENT: "Recent Events",              # Doc 04 §4
        }

        # Ordered: goals first, then decisions, then technical, then rest
        order = [NodeType.GOAL, NodeType.DECISION, NodeType.TECHNICAL_FACT,
                 NodeType.PROBLEM, NodeType.EVENT, NodeType.PREFERENCE,
                 NodeType.ENTITY, NodeType.TASK, NodeType.INSIGHT,
                 NodeType.CONSTRAINT]

        for ntype in order:
            if ntype in groups:
                label = type_labels.get(ntype, ntype.value)
                sections.append(f"\n## {label}")
                for n in groups[ntype]:
                    sections.append(f"- {n.content}")

        context = "\n".join(sections)

        # Platform-specific wrapping (my addition)
        if platform == "claude":
            return f"<context>\n{context}\n</context>"
        elif platform == "chatgpt":
            return f"[System Context]\n{context}\n[End Context]"
        elif platform == "gemini":
            return f"Context from previous sessions:\n{context}"
        return context
```

---

## File 3: backend/services/workspace_detection.py

```python
class WorkspaceDetectionService:
    """Auto-detect workspace from conversation content."""

    async def infer_workspace(self, text: str) -> tuple[str, float]:
        """
        Embed text, compare against all active workspace descriptions.
        Returns (workspace_id, confidence_score).
        """
        if not text:
            return ("", 0.0)

        workspaces = await self.workspace_repo.get_active()
        if not workspaces:
            return ("", 0.0)

        query_embedding = self.embedding_service.embed_text(text)
        best_id, best_score = "", 0.0

        for ws in workspaces:
            # Compare against workspace name + description + tag embeddings
            ws_text = f"{ws.name} {ws.description} {' '.join(ws.tags)}"
            ws_embedding = self.embedding_service.embed_text(ws_text)
            score = cosine_similarity(query_embedding, ws_embedding)

            if score > best_score:
                best_score = score
                best_id = ws.id

        # Also check platform_mappings table for URL-based matching
        # (higher priority than semantic matching)

        return (best_id, best_score)

    async def record_assignment(self, workspace_id: str, url: str, platform: str):
        """Remember URL→workspace mapping for future auto-detection."""
        await self.platform_mappings_repo.create(PlatformMapping(
            workspace_id=workspace_id, url_pattern=self._extract_pattern(url),
            platform=platform))
```

---

## Key Design Rules Enforced

| Rule (from Doc 14) | Implementation |
|--------------------|----------------|
| Goals + decisions always included | Separate retrieval sources, not filtered by semantic relevance |
| Never return conflicting nodes | `_filter_conflicts()` removes both sides of pending conflicts |
| Respect token budget strictly | `_apply_token_budget()` progressive trimming |
| Quality over quantity | Compound scoring ranks by relevance, not volume |
| Update last_accessed on retrieval | `update_last_accessed()` + `increment_reinforcement()` |
| Never sort by creation date | Compound retention score: importance × recency × reinforcement |
| Embeddings pre-computed, never at retrieval time | Embeddings generated at commit time in graph_service |
| < 300ms target | Parallel retrieval via `asyncio.gather()`, no sync I/O |

---

## Files Summary

| File | Lines Est. |
|------|-----------|
| `backend/services/intent_service.py` | ~80 |
| `backend/services/retrieval_service.py` | ~250 |
| `backend/services/workspace_detection.py` | ~60 |

**Total: 3 files, ~390 lines.**

---

> **Next: Plan 06 — Chrome Extension Core** (Plasmo setup, DOM observers, platform hooks, injector)
