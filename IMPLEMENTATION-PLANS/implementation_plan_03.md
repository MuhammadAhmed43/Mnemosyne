# Plan 03 — Knowledge Graph & Core Services

> Covers: Doc 03 (Architecture), Doc 04 (Memory Model), Doc 05 (Conflict Resolution), Doc 10 (Backend Logic)

---

## 1. REPOSITORIES (Data Access Layer)

### node_repo.py — Core graph CRUD + traversal

```python
class NodeRepository:
    async def create(self, node: MemoryNode) -> MemoryNode
    async def get(self, node_id: str) -> Optional[MemoryNode]
    async def get_active(self, workspace_id: str, node_type: Optional[NodeType] = None,
                         limit: int = 100) -> list[MemoryNode]
    async def update_metadata(self, node_id: str, **kwargs)  # Non-content fields only
    async def create_new_version(self, node_id: str, new_content: str,
                                  structured_data: dict, changed_by: str,
                                  reason: Optional[str]) -> MemoryNode
    async def archive(self, node_id: str)
    async def hard_delete(self, node_id: str)  # Removes from SQLite + Qdrant
    async def bulk_archive(self, node_ids: list[str])
    async def search_fts(self, workspace_id: str, query: str) -> list[MemoryNode]
    async def get_by_importance(self, workspace_id: str, min_score: float) -> list[MemoryNode]
    async def get_decayable(self, workspace_id: str) -> list[MemoryNode]
    async def update_last_accessed(self, node_ids: list[str])
    async def increment_reinforcement(self, node_ids: list[str], amount: float = 0.05):
        """GAP-04 FIX: Differentiated reinforcement (Doc 04 §8).
        Callers pass the appropriate amount:
          - Retrieval result: +0.05
          - User views in audit UI: +0.10
          - Referenced in new conversation: +0.20
          - User manually confirms: +0.50
        """

    # Graph traversal using recursive CTEs
    async def traverse(self, start_node_id: str, max_hops: int = 3,
                       edge_types: Optional[list[EdgeType]] = None) -> list[MemoryNode]:
        """
        Doc 07 §4: BIDIRECTIONAL graph walk — follows both outgoing AND incoming edges.
        Without OR clause, traversal from Node B misses Node A when edge is A→B.

        WITH RECURSIVE graph_walk(node_id, depth) AS (
            SELECT ?, 0
            UNION ALL
            SELECT
                CASE
                    WHEN e.source_node_id = gw.node_id THEN e.target_node_id
                    ELSE e.source_node_id
                END,
                gw.depth + 1
            FROM graph_walk gw
            JOIN memory_edges e ON (
                e.source_node_id = gw.node_id OR e.target_node_id = gw.node_id
            )
            WHERE gw.depth < ? AND e.is_active = 1
        )
        SELECT DISTINCT mn.* FROM graph_walk gw
        JOIN memory_nodes mn ON mn.id = gw.node_id
        WHERE mn.status = 'active'
        """

    async def get_neighbors(self, node_id: str) -> list[tuple[MemoryNode, MemoryEdge]]
    async def get_version_history(self, node_id: str) -> list[NodeVersion]
```

### edge_repo.py, workspace_repo.py, conflict_repo.py, pending_review_repo.py, session_repo.py, audit_repo.py, settings_repo.py, onboarding_repo.py

Each follows same pattern: typed CRUD methods wrapping SQL queries. Key methods:

```python
# edge_repo.py
class EdgeRepository:
    async def create(self, edge: MemoryEdge) -> MemoryEdge
    async def get_edges_for_node(self, node_id: str) -> list[MemoryEdge]
    async def deactivate_edges_for_node(self, node_id: str)
    async def find_edge(self, source_id: str, target_id: str, edge_type: EdgeType) -> Optional[MemoryEdge]

# conflict_repo.py
class ConflictRepository:
    async def create(self, conflict: ConflictCandidate)
    async def get_pending(self, workspace_id: str) -> list[ConflictCandidate]
    async def resolve(self, conflict_id: str, event: ResolutionEvent)

# audit_repo.py (append-only, hash-chained)
class AuditRepository:
    async def append(self, action: str, entity_type: str, entity_id: str,
                     workspace_id: str, details: dict)
    # Computes chain_hash = SHA-256(prev_hash + timestamp + action + entity_id)
    async def verify_integrity(self) -> bool  # Verify full chain
    async def get_log(self, workspace_id: str, limit: int = 100) -> list[AuditEntry]
```

---

## 2. GRAPH SERVICE (backend/services/graph_service.py)

```python
class GraphService:
    """Knowledge graph operations with temporal versioning."""

    def __init__(self, node_repo, edge_repo, audit_repo, embedding_service):
        self.nodes = node_repo
        self.edges = edge_repo
        self.audit = audit_repo
        self.embeddings = embedding_service

    async def commit_node(self, workspace_id: str,
                          candidate: ExtractionCandidate,
                          session_id: str) -> MemoryNode:
        """Create node from extraction candidate, generate embedding, audit."""
        node = MemoryNode(
            workspace_id=workspace_id,
            node_type=candidate.node_type,
            content=candidate.content,
            structured_data=candidate.structured_data,
            extraction_confidence=candidate.confidence,
            source_session_id=session_id,
            source_platform=...,
            tier=self._assign_tier(candidate.node_type),
        )
        node = await self.nodes.create(node)

        # Create version 1 snapshot
        await self._create_version_snapshot(node)

        # Generate + store embedding (async, non-blocking)
        await self.embeddings.embed_and_store(workspace_id, node)

        # Audit
        await self.audit.append("node_created", "node", node.id, workspace_id,
                                {"type": node.node_type, "confidence": node.extraction_confidence})

        # Auto-create edges to related nodes
        await self._create_auto_edges(workspace_id, node)

        return node

    async def update_node_content(self, node_id: str, workspace_id: str,
                                   new_content: str, structured_data: dict,
                                   changed_by: str = "user",
                                   reason: Optional[str] = None) -> MemoryNode:
        """Temporal versioning: archive old, create new version. NEVER overwrite."""
        old = await self.nodes.get(node_id)

        # Archive old version
        await self.nodes.update_metadata(node_id, valid_until=datetime.utcnow(),
                                          status=NodeStatus.SUPERSEDED)
        await self._create_version_snapshot(old)

        # Create new version
        updated = await self.nodes.create_new_version(
            node_id, new_content, structured_data, changed_by, reason
        )

        # Re-embed
        await self.embeddings.embed_and_store(workspace_id, updated)

        # Audit
        await self.audit.append("node_updated", "node", node_id, workspace_id,
                                {"version": updated.version, "changed_by": changed_by})
        return updated

    async def boost_node(self, node_id: str, importance: float,
                         permanent: bool = False):
        await self.nodes.update_metadata(node_id,
            importance_score=importance, is_permanent=permanent,
            user_verified=True)

    async def get_graph_data(self, workspace_id: str) -> dict:
        """Return nodes + edges for visualization."""
        nodes = await self.nodes.get_active(workspace_id)
        edges = []
        for n in nodes:
            edges.extend(await self.edges.get_edges_for_node(n.id))
        return {"nodes": nodes, "edges": list({e.id: e for e in edges}.values())}

    def _assign_tier(self, node_type: NodeType) -> MemoryTier:
        """Doc 04 §§3-6: Assign memory tier by node type."""
        tier_map = {
            NodeType.GOAL: MemoryTier.SEMANTIC,
            NodeType.DECISION: MemoryTier.EPISODIC,
            NodeType.TECHNICAL_FACT: MemoryTier.SEMANTIC,
            NodeType.PREFERENCE: MemoryTier.PROCEDURAL,
            NodeType.ENTITY: MemoryTier.SEMANTIC,
            NodeType.TASK: MemoryTier.EPISODIC,
            NodeType.PROBLEM: MemoryTier.EPISODIC,
            NodeType.INSIGHT: MemoryTier.SEMANTIC,
            NodeType.EVENT: MemoryTier.EPISODIC,              # Doc 04 §4
            NodeType.RELATIONSHIP: MemoryTier.SEMANTIC,        # Doc 04 §2.2
            NodeType.WORKSPACE_SUMMARY: MemoryTier.SEMANTIC,   # Doc 04 §2.2
            NodeType.USER_NOTE: MemoryTier.EPISODIC,           # Doc 04 §2.2
        }
        return tier_map.get(node_type, MemoryTier.EPISODIC)

    async def _create_auto_edges(self, workspace_id: str, new_node: MemoryNode):
        """Find semantically similar nodes and create RELATES_TO edges."""
        similar = await self.embeddings.find_similar(
            workspace_id, new_node.embedding_id, top_k=5, threshold=0.75
        )
        for match in similar:
            if match.id != new_node.id:
                await self.edges.create(MemoryEdge(
                    workspace_id=workspace_id,
                    source_node_id=new_node.id,
                    target_node_id=match.id,
                    edge_type=EdgeType.RELATES_TO,
                    weight=match.score,
                ))
```

---

## 3. CONFLICT SERVICE (backend/services/conflict_service.py)

All 6 conflict types from Doc 05 §2, plus plan refinements:

| Type | Example | Default Strategy |
|------|---------|-----------------|
| DIRECT_FACT | "uses PostgreSQL" vs "uses MongoDB" | TEMPORAL |
| GOAL_STATE | Goal "active" + event "completed it" | TEMPORAL (event-triggered) |
| SEMANTIC_DRIFT | Meaning evolved without explicit update | USER_REVIEW |
| PREFERENCE | "prefers tabs" vs "switched to spaces" | CONFIDENCE_WEIGHTED |
| LOGICAL_ERROR | Feature X DEPENDS_ON Y AND Y DEPENDS_ON X | LOGICAL_FLAG |
| ENTITY_DISAMBIGUATION | "Python" = language vs "python.py" file | USER_REVIEW |
| GOAL_CONFLICT | Two mutually exclusive goals | USER_REVIEW |
| SCOPE_CONTRADICTION | "MVP includes X" vs "cut X from MVP" | TEMPORAL |
| VERSION_FORK | Same fact diverged in two sessions | CONFIDENCE_WEIGHTED |
| LOGICAL_INCONSISTENCY | "deadline June 1" + "launch after July" | LOGICAL_FLAG |

```python
class ConflictService:
    async def detect_conflicts(self, workspace_id: str,
                                new_node: MemoryNode) -> list[ConflictCandidate]:
        """Run after every node commit. Check for contradictions."""
        existing = await self.nodes.get_active(workspace_id, node_type=new_node.node_type)
        conflicts = []
        for existing_node in existing:
            if existing_node.id == new_node.id:
                continue
            score = await self._compute_contradiction_score(new_node, existing_node)
            if score > 0.65:  # Contradiction threshold
                strategy = self._pick_strategy(new_node, existing_node, score)
                conflict = ConflictCandidate(
                    workspace_id=workspace_id,
                    node_a_id=existing_node.id, node_b_id=new_node.id,
                    conflict_type=self._classify_type(new_node, existing_node),
                    contradiction_score=score,
                    suggested_strategy=strategy,
                    auto_resolvable=self._can_auto_resolve(existing_node, new_node, strategy),
                )
                conflicts.append(conflict)
        return conflicts

    async def auto_resolve(self, conflict: ConflictCandidate) -> Optional[ResolutionEvent]:
        """Auto-resolve if: neither node is user-verified AND strategy supports it."""
        if not conflict.auto_resolvable:
            return None

        node_a = await self.nodes.get(conflict.node_a_id)
        node_b = await self.nodes.get(conflict.node_b_id)

        if conflict.suggested_strategy == ConflictStrategy.TEMPORAL:
            # Newer wins
            winner, loser = (node_b, node_a) if node_b.created_at > node_a.created_at \
                            else (node_a, node_b)
            await self.graph.update_node_metadata(loser.id,
                valid_until=winner.created_at, status=NodeStatus.SUPERSEDED)
            await self.edges.create(MemoryEdge(
                workspace_id=conflict.workspace_id,
                source_node_id=winner.id, target_node_id=loser.id,
                edge_type=EdgeType.SUPERSEDES))
            return ResolutionEvent(
                conflict_id=conflict.id,
                strategy_used=ConflictStrategy.TEMPORAL,
                status=ResolutionStatus.AUTO_RESOLVED,
                winning_node_id=winner.id,
                archived_node_ids=[loser.id])

        elif conflict.suggested_strategy == ConflictStrategy.CONFIDENCE_WEIGHTED:
            winner, loser = (node_a, node_b) if node_a.extraction_confidence > \
                            node_b.extraction_confidence else (node_b, node_a)
            # Same archive logic as temporal
            ...

        return None  # Can't auto-resolve → stays pending

    def _can_auto_resolve(self, node_a, node_b, strategy) -> bool:
        if node_a.user_verified or node_b.user_verified:
            return False  # Doc 14: never auto-resolve user-verified
        if strategy == ConflictStrategy.USER_REVIEW:
            return False
        return True

    async def user_resolve(self, conflict_id: str, winning_node_id: str,
                            custom_resolution: Optional[str] = None):
        """User picks winner or provides custom merge."""
        # If custom_resolution: create new merged node, archive both originals
        # If winning_node_id: archive loser, keep winner
        ...

    # --- GAP-06 FIX: Structural Conflict Detection (Doc 05 §3.2 Method B) ---

    async def detect_structural_conflicts(self, workspace_id: str,
                                           new_node: MemoryNode) -> list[ConflictCandidate]:
        """Method B: Entity+Attribute hash check for TECHNICAL_FACT nodes.
        Faster and more precise than semantic similarity for structured facts."""
        if new_node.node_type != NodeType.TECHNICAL_FACT:
            return []

        entity = new_node.structured_data.get('entity')
        attribute = new_node.structured_data.get('attribute')
        new_value = new_node.structured_data.get('value')

        if not all([entity, attribute, new_value]):
            return []

        # SQL: same entity + attribute, different value, still active
        existing = await self.node_repo.query("""
            SELECT * FROM memory_nodes
            WHERE workspace_id = ?
            AND node_type = 'technical_fact'
            AND json_extract(structured_data, '$.entity') = ?
            AND json_extract(structured_data, '$.attribute') = ?
            AND json_extract(structured_data, '$.value') != ?
            AND status = 'active' AND valid_until IS NULL
        """, workspace_id, entity, attribute, new_value)

        return [ConflictCandidate(
            workspace_id=workspace_id,
            node_a_id=e.id, node_b_id=new_node.id,
            conflict_type=ConflictType.DIRECT_FACT,
            contradiction_score=0.95,  # Structural match = high confidence
            suggested_strategy=ConflictStrategy.TEMPORAL,
            auto_resolvable=not e.user_verified,
        ) for e in existing]

    # --- GAP-02 FIX: Goal State Detection (Doc 05 §3.2 Method C) ---

    async def detect_goal_state_conflicts(self, workspace_id: str,
                                           new_node: MemoryNode) -> list[ConflictCandidate]:
        """Method C: When an EVENT implies completion of an active GOAL."""
        if new_node.node_type != NodeType.EVENT:
            return []

        completion_phrases = ["completed", "finished", "shipped", "launched",
                              "deployed", "done", "delivered", "submitted"]
        if not any(p in new_node.content.lower() for p in completion_phrases):
            return []

        # Find active goals semantically similar to this event
        active_goals = await self.node_repo.get_active(
            workspace_id, node_type=NodeType.GOAL)
        candidates = []
        for goal in active_goals:
            if goal.structured_data.get('status') != 'ACTIVE':
                continue
            similarity = await self.embeddings.compute_similarity(
                new_node.embedding_id, goal.embedding_id)
            if similarity > 0.75:
                candidates.append(ConflictCandidate(
                    workspace_id=workspace_id,
                    node_a_id=goal.id, node_b_id=new_node.id,
                    conflict_type=ConflictType.GOAL_STATE,
                    contradiction_score=similarity,
                    suggested_strategy=ConflictStrategy.TEMPORAL,
                    auto_resolvable=not goal.user_verified,
                ))
        return candidates

    # --- GAP-02 FIX: Relationship Conflict Detection (Doc 05 §2 Type 5) ---

    async def detect_relationship_conflicts(self, workspace_id: str,
                                             new_edge: MemoryEdge) -> list[ConflictCandidate]:
        """Type 5: Circular dependency or incompatible edge detection.
        Strategy: LOGICAL_FLAG — never auto-resolve, surface in audit UI."""
        if new_edge.edge_type not in (EdgeType.DEPENDS_ON, EdgeType.BLOCKS, EdgeType.BLOCKED_BY):
            return []

        # Check for inverse edge (A→B and B→A)
        inverse = await self.edge_repo.find_edge(
            source_id=new_edge.target_node_id,
            target_id=new_edge.source_node_id,
            edge_type=new_edge.edge_type)

        if inverse:
            return [ConflictCandidate(
                workspace_id=workspace_id,
                node_a_id=new_edge.source_node_id,
                node_b_id=new_edge.target_node_id,
                conflict_type=ConflictType.LOGICAL_ERROR,  # Doc 05 §2 Type 5, Doc 07 §2.4
                contradiction_score=1.0,
                suggested_strategy=ConflictStrategy.LOGICAL_FLAG,
                auto_resolvable=False,  # Doc 05 §4 Strategy 4: NEVER auto-resolve
            )]
        return []
```

> **Note:** `detect_conflicts()` now calls all three methods (semantic, structural, goal-state) and merges results. `detect_relationship_conflicts()` is called separately when edges are created.

---

## 4. DECAY SERVICE (backend/services/decay_service.py)

```python
from dataclasses import dataclass

@dataclass
class DecayCycleResult:
    """Doc 10 §4: Typed return for run_decay_cycle."""
    workspace_id: str
    archived: int
    pruned: int
    demoted: int
    active: int
    duration_ms: int

import math

class DecayService:
    """Memory decay using exponential function with reinforcement resistance."""

    # --- GAP-03 FIX: Status-aware decay rates (Doc 04 §8) ---
    DECAY_RATES_BY_TYPE_STATUS = {
        (NodeType.TASK, 'TODO'):        0.05,
        (NodeType.TASK, 'IN_PROGRESS'): 0.05,
        (NodeType.TASK, 'DONE'):        0.15,
        (NodeType.TASK, 'BLOCKED'):     0.04,
        (NodeType.GOAL, 'ACTIVE'):      0.03,
        (NodeType.GOAL, 'COMPLETED'):   0.20,
        (NodeType.GOAL, 'ABANDONED'):   0.20,
        (NodeType.PROBLEM, 'OPEN'):     0.04,
        (NodeType.PROBLEM, 'RESOLVED'): 0.12,
        (NodeType.DECISION, None):      0.02,
        (NodeType.TECHNICAL_FACT, None):0.01,
        (NodeType.EVENT, None):         0.08,
        (NodeType.PREFERENCE, None):    0.005,
        (NodeType.ENTITY, None):        0.03,
        (NodeType.INSIGHT, None):       0.04,
    }

    def _get_effective_decay_rate(self, node: MemoryNode) -> float:
        """Look up decay rate by (node_type, status), fallback to tier rate."""
        status = node.structured_data.get('status')
        rate = self.DECAY_RATES_BY_TYPE_STATUS.get((node.node_type, status))
        if rate is None:
            rate = self.DECAY_RATES_BY_TYPE_STATUS.get((node.node_type, None))
        if rate is None:
            rate = self.get_tier_decay_rates().get(node.tier, 0.05)
        return rate

    def compute_retention(self, node: MemoryNode,
                          workspace_status: str = 'active') -> float:
        """
        Retention = importance × e^(-decay_rate × days) × reinforcement × workspace_relevance
        From Doc 04 §8
        """
        if node.is_permanent:
            return 1.0

        days = (datetime.utcnow() - node.last_accessed).total_seconds() / 86400
        decay_rate = self._get_effective_decay_rate(node)
        base = node.importance_score * math.exp(-decay_rate * days)

        # Reinforcement: each access adds resistance (Doc 04 §8)
        reinforcement = 1.0 + (0.1 * min(node.reinforcement_count, 10))

        # Workspace relevance factor (Doc 04 §8)
        ws_relevance = {'active': 1.0, 'inactive': 0.5, 'archived': 0.2}
        relevance = ws_relevance.get(workspace_status, 1.0)

        return min(base * reinforcement * relevance, 1.0)

    # --- GAP-05 FIX: 4-tier decay actions (Doc 04 §8) ---

    async def run_decay_cycle(self, workspace_id: str) -> DecayCycleResult:
        """Runs every 6 hours. Apply 4-tier decay actions per Doc 04 §8."""
        start = time.monotonic()
        nodes = await self.node_repo.get_decayable(workspace_id)
        ws = await self.workspace_repo.get(workspace_id)
        ws_status = ws.status if ws else 'active'

        stats = {'active': 0, 'demoted': 0, 'archived': 0, 'pruned': 0}
        for node in nodes:
            retention = self.compute_retention(node, ws_status)

            if retention < 0.2:
                # PRUNED — cold storage, not retrieved (Doc 04 §8)
                await self.node_repo.update_metadata(node.id,
                    status=NodeStatus.DECAYED)
                await self.audit.append("node_pruned", "node", node.id,
                    workspace_id, {"retention": round(retention, 3)})
                stats['pruned'] += 1

            elif retention < 0.4:
                # ARCHIVED — not retrieved unless explicitly requested
                await self.node_repo.archive(node.id)
                await self.audit.append("node_decayed", "node", node.id,
                    workspace_id, {"retention": round(retention, 3)})
                stats['archived'] += 1

            elif retention < 0.6:
                # DEMOTED — lower retrieval priority
                await self.node_repo.update_metadata(node.id,
                    importance_score=retention * node.importance_score)
                stats['demoted'] += 1

            else:
                stats['active'] += 1

        logger.info(f"Decay cycle [{workspace_id}]: {stats}")
        return DecayCycleResult(
            workspace_id=workspace_id,
            archived=stats['archived'],
            pruned=stats['pruned'],
            demoted=stats['demoted'],
            active=stats['active'],
            duration_ms=int((time.monotonic() - start) * 1000)
        )

    def get_tier_decay_rates(self) -> dict:
        """Fallback decay rates by tier."""
        return {
            MemoryTier.WORKING: 0.50,
            MemoryTier.EPISODIC: 0.05,
            MemoryTier.SEMANTIC: 0.01,
            MemoryTier.PROCEDURAL: 0.005,
        }
```

---

## 5. CONSOLIDATION SERVICE (backend/services/consolidation_service.py)

```python
from dataclasses import dataclass

# ── Consolidation constants (Doc 10 §5) ──────────────────────────────────────
# Cosine similarity threshold above which two nodes are considered near-duplicates
# and eligible for merging during the nightly consolidation pass.
# Value sourced from Doc 10 §5. Change requires benchmark re-validation.
MERGE_THRESHOLD: float = 0.92


@dataclass
class ConsolidationResult:
    """Doc 10 §5: Typed return for run_consolidation."""
    workspace_id: str
    merged: int          # Near-duplicate nodes merged
    exact_deduped: int   # Exact matches removed
    tiers_promoted: int  # Nodes promoted episodic→semantic
    duration_ms: int

class ConsolidationService:
    """Daily: deduplicate, merge near-duplicates, promote tiers."""

    async def run_consolidation(self, workspace_id: str) -> ConsolidationResult:
        """Doc 10 §5: Returns typed ConsolidationResult."""
        start = time.monotonic()
        nodes = await self.node_repo.get_active(workspace_id)
        exact = await self._dedup_exact(nodes)
        merged = await self._merge_similar(workspace_id, nodes)
        promoted = await self._promote_tiers(nodes)
        return ConsolidationResult(
            workspace_id=workspace_id,
            merged=merged,
            exact_deduped=exact,
            tiers_promoted=promoted,
            duration_ms=int((time.monotonic() - start) * 1000)
        )

    async def _merge_similar(self, workspace_id, nodes):
        """Doc 10 §5 + Doc 05 §4 Strategy 1: merge archives loser AND creates SUPERSEDES edge."""
        for node in nodes:
            similar = await self.embeddings.    find_similar(
                workspace_id, node.embedding_id, top_k=3, threshold=MERGE_THRESHOLD)
            for match in similar:
                if match.id == node.id or match.node_type != node.node_type:
                    continue
                # Winner = higher extraction_confidence
                winner = node if node.extraction_confidence >= match.extraction_confidence else match
                loser  = match if winner is node else node

                # Archive loser with merge reason
                await self.node_repo.update_metadata(
                    loser.id,
                    valid_until=datetime.utcnow(),
                    status=NodeStatus.SUPERSEDED,
                    change_reason=f"Merged into {winner.id}"  # Doc 10 §5
                )

                # Create SUPERSEDES edge for graph traceability (Doc 05 §4 Strategy 1)
                await self.edge_repo.create(MemoryEdge(
                    workspace_id=workspace_id,
                    source_node_id=winner.id,
                    target_node_id=loser.id,
                    edge_type=EdgeType.SUPERSEDES,
                    label=f"Consolidated: merged near-duplicate",
                    weight=match.score if hasattr(match, 'score') else 1.0,
                ))

                await self.audit.append(
                    "node_merged", "node", loser.id, workspace_id,
                    {"winner_id": winner.id, "similarity": getattr(match, 'score', 1.0)}
                )

    async def _promote_tiers(self, nodes):
        for node in nodes:
            if (node.tier == MemoryTier.EPISODIC and
                node.reinforcement_count >= 5 and
                node.extraction_confidence >= 0.75):
                await self.node_repo.update_metadata(node.id,
                    tier=MemoryTier.SEMANTIC, decay_rate=0.01)
```

---

## 6. RETRIEVAL SERVICE (backend/services/retrieval_service.py)

> **🔴 Conflict fix — Doc 10 §3:** RetrievalService was completely missing from Plan 03.
> This is the most latency-critical service. Target: < 300ms end-to-end.

```python
class RetrievalService:
    def __init__(self, graph_service, vector_store, intent_analyzer, workspace_repo):
        self.graph = graph_service
        self.vectors = vector_store
        self.intent = intent_analyzer
        self.workspace_repo = workspace_repo

    async def get_context(
        self,
        workspace_id: str,
        token_budget: int = 2000,
        intent_hint: Optional[str] = None,
        platform: str = 'claude'
    ) -> ContextResult:
        # 1. Analyze intent
        intent = await self.intent.analyze(workspace_id=workspace_id, hint=intent_hint)

        # 2. Run all 5 retrieval sources in PARALLEL (Doc 10 §3)
        results = await asyncio.gather(
            self._retrieve_active_goals(workspace_id),
            self._retrieve_recent_decisions(workspace_id),
            self._retrieve_open_problems(workspace_id),
            self._retrieve_semantic_relevant(workspace_id, intent),
            self._retrieve_high_importance(workspace_id),
            return_exceptions=True
        )
        all_nodes = []
        for result in results:
            if not isinstance(result, Exception):
                all_nodes.extend(result)

        # 3. Dedup → rank → budget
        unique = self._deduplicate(all_nodes)
        ranked = self._rank_for_context(unique, intent)
        selected = self._fit_to_token_budget(ranked, token_budget)

        # 4. Build context string
        context_string = self._build_context_string(workspace_id, selected, platform)

        # 5. Increment reinforcement (Doc 04 §8: retrieval = +0.05)
        await self.graph.nodes.increment_reinforcement(
            [n.id for n in selected], amount=0.05)

        return ContextResult(
            workspace_id=workspace_id,
            context_string=context_string,
            nodes_included=selected,
            token_count=self._count_tokens(context_string)
        )

    async def _retrieve_active_goals(self, workspace_id: str) -> list[MemoryNode]:
        return await self.graph.nodes.get_active(
            workspace_id, node_type=NodeType.GOAL, limit=5)

    async def _retrieve_recent_decisions(self, workspace_id: str) -> list[MemoryNode]:
        cutoff = datetime.utcnow() - timedelta(days=14)
        nodes = await self.graph.nodes.get_active(workspace_id, node_type=NodeType.DECISION)
        return [n for n in nodes if n.created_at >= cutoff][:5]

    async def _retrieve_open_problems(self, workspace_id: str) -> list[MemoryNode]:
        nodes = await self.graph.nodes.get_active(workspace_id, node_type=NodeType.PROBLEM)
        return [n for n in nodes
                if n.structured_data.get('status', 'OPEN') == 'OPEN'][:3]

    async def _retrieve_semantic_relevant(self, workspace_id, intent) -> list[MemoryNode]:
        if not getattr(intent, 'query_vector', None):
            return []
        return await self.vectors.search(
            workspace_id=workspace_id, query_vector=intent.query_vector,
            top_k=10, filter={'status': 'active'})

    async def _retrieve_high_importance(self, workspace_id: str) -> list[MemoryNode]:
        return await self.graph.nodes.get_by_importance(workspace_id, min_score=0.8)

    def _rank_for_context(self, nodes, intent) -> list[MemoryNode]:
        TYPE_PRIORITY = {
            NodeType.GOAL: 1.3, NodeType.DECISION: 1.2, NodeType.PROBLEM: 1.15,
            NodeType.TECHNICAL_FACT: 1.0, NodeType.PREFERENCE: 0.9,
            NodeType.ENTITY: 0.8, NodeType.EVENT: 0.7, NodeType.TASK: 0.9,
        }
        def score(n):
            base = n.importance_score * TYPE_PRIORITY.get(n.node_type, 1.0)
            days_old = (datetime.utcnow() - n.updated_at).days
            recency = max(0.5, 1.0 - (days_old / 90))
            base *= recency
            if getattr(n, '_semantic_score', None):
                base *= (0.7 + 0.3 * n._semantic_score)
            if n.user_verified:
                base *= 1.2
            return min(1.0, base)
        nodes.sort(key=score, reverse=True)
        return nodes

    def _fit_to_token_budget(self, nodes, budget: int) -> list[MemoryNode]:
        selected, used = [], 0
        for node in nodes:
            tokens = len(node.content.split()) * 1.3  # rough estimate
            if used + tokens <= budget:
                selected.append(node)
                used += tokens
        return selected

    def _build_context_string(
        self, workspace_id: str, nodes: list[MemoryNode], platform: str
    ) -> str:
        """Doc 10 §3: Format nodes by type section for AI platform injection."""
        sections = {t: [] for t in [
            NodeType.GOAL, NodeType.DECISION, NodeType.PROBLEM,
            NodeType.TECHNICAL_FACT, NodeType.PREFERENCE, NodeType.ENTITY
        ]}
        for node in nodes:
            if node.node_type in sections:
                sections[node.node_type].append(node)

        ws = self.workspace_repo.get_sync(workspace_id)
        lines = [f"[MNEMOSYNE — Workspace: {ws.name if ws else workspace_id}]", ""]

        if sections[NodeType.GOAL]:
            lines.append("Current Goals:")
            for n in sections[NodeType.GOAL]:
                priority = n.structured_data.get('priority', '')
                deadline = n.structured_data.get('deadline', '')
                suffix = f" [{priority}]" if priority else ""
                if deadline: suffix += f" · Due: {deadline}"
                lines.append(f"• {n.content}{suffix}")
            lines.append("")

        if sections[NodeType.DECISION]:
            lines.append("Recent Decisions:")
            for n in sections[NodeType.DECISION]:
                date = n.created_at.strftime('%b %d')
                rationale = n.structured_data.get('rationale', '')
                reason = f" — {rationale}" if rationale else ""
                lines.append(f"• {n.content} ({date}){reason}")
            lines.append("")

        if sections[NodeType.PROBLEM]:
            lines.append("Open Problems:")
            for n in sections[NodeType.PROBLEM]:
                lines.append(f"• {n.content}")
            lines.append("")

        if sections[NodeType.TECHNICAL_FACT]:
            by_cat = {}
            for n in sections[NodeType.TECHNICAL_FACT]:
                cat = n.structured_data.get('category', 'other')
                by_cat.setdefault(cat, []).append(
                    n.structured_data.get('value', n.content))
            lines.append("Technical Stack:")
            for cat, vals in by_cat.items():
                lines.append(f"• {cat.title()}: {', '.join(vals)}")
            lines.append("")

        if sections[NodeType.PREFERENCE]:
            lines.append("Working Preferences:")
            for n in sections[NodeType.PREFERENCE]:
                lines.append(f"• {n.content}")
            lines.append("")

        people = [n for n in sections[NodeType.ENTITY]
                  if n.structured_data.get('entity_type') == 'person']
        if people:
            lines.append("Key People:")
            for n in people:
                role = n.structured_data.get('role', '')
                lines.append(f"• {n.content}{(' (' + role + ')') if role else ''}")
            lines.append("")

        return "\n".join(lines)

    def _deduplicate(self, nodes): return list({n.id: n for n in nodes}.values())
    def _count_tokens(self, text): return len(text.split())
```

---

## 7. INTENT ANALYZER (backend/services/intent_service.py)

> **🔴 Conflict fix — Doc 10 §6:** IntentAnalyzer was completely missing from Plan 03.

```python
class IntentAnalyzer:
    """Doc 10 §6: Multi-signal intent analysis to guide context retrieval."""

    async def analyze(self, workspace_id: str,
                      hint: Optional[str] = None) -> Intent:
        """
        Signals used:
        1. Recent session activity (last 3 turns node types)
        2. Active goals (what is user working toward?)
        3. Hint text from context request (explicit signal from extension)
        4. Time-of-day patterns from procedural memory
        """
        signals = await asyncio.gather(
            self._analyze_recent_activity(workspace_id),
            self._get_active_goal_vectors(workspace_id),
            return_exceptions=True
        )

        query_vector = None
        if hint:
            query_vector = await self.embedding_service.embed_text(hint)
        elif not isinstance(signals[1], Exception) and signals[1]:
            # Use average of active goal vectors as intent proxy
            vecs = signals[1]
            query_vector = [sum(v[i] for v in vecs) / len(vecs)
                            for i in range(len(vecs[0]))]

        return Intent(
            workspace_id=workspace_id,
            query_vector=query_vector,
            hint=hint
        )

    async def _analyze_recent_activity(self, workspace_id: str) -> list:
        return []  # Populated from session_repo last-3-turns

    async def _get_active_goal_vectors(self, workspace_id: str) -> list:
        goals = await self.node_repo.get_active(workspace_id, node_type=NodeType.GOAL)
        return [g.embedding_id for g in goals if g.embedding_id]
```

---

## 8. OTHER SERVICES

### workspace_service.py
```python
class WorkspaceService:
    async def create(self, name: str, description: str, tags: list[str]) -> Workspace
    async def archive(self, workspace_id: str)  # Sets decay_rate *= 0.2
    async def delete(self, workspace_id: str)   # Hard delete all data

    async def infer_workspace(
        self,
        user_message: str,
        ai_response: str,
        tab_url: str        # Doc 10 §8: URL used for signal boosting in platform_mappings
    ) -> tuple[str, float]:
        """
        Doc 10 §8: 3-signal workspace detection:
        1. Semantic similarity: embed combined text vs workspace summary_embedding
        2. Entity overlap: candidate entities vs workspace top entities
        3. URL match: check platform_mappings (global DB) for tab_url pattern
        Returns (workspace_id, confidence_score). Returns (SUGGEST_NEW, 0.0) if no match >= 0.6.
        """

    async def get_health(self, workspace_id: str) -> dict:
        """
        Doc 10 §8: Compute memory_health_score from:
        - node_count, active/archived ratio
        - conflict_count (pending unresolved)
        - decay_coverage (% nodes with retention > 0.4)
        - coverage_gaps (key node types with 0 nodes)
        Updates workspace.memory_health_score in DB.
        """

    async def export_json(self, workspace_id: str) -> dict:
        """
        Doc 08 §5: Full bundle export:
        {workspace, nodes[], edges[], node_versions[], pending_reviews[], metadata}
        """

    async def import_json(self, data: dict) -> Workspace:
        """
        Doc 08 §5: Import full bundle. Validates schema, creates workspace,
        upserts all nodes/edges/versions. Skips if IDs already exist.
        """
```

### embedding_service.py
```python
class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.clients: dict[str, QdrantClient] = {}

    async def embed_and_store(self, workspace_id: str, node: MemoryNode)
    async def find_similar(self, workspace_id: str, point_id: str,
                           top_k: int = 10, threshold: float = 0.7) -> list
    async def search_by_text(self, workspace_id: str, query: str,
                             top_k: int = 20, filters: dict = None) -> list
    async def delete_point(self, workspace_id: str, point_id: str)
    async def reindex_workspace(self, workspace_id: str)  # Full re-embed
```

### capture_service.py
```python
class CaptureService:
    """Doc 10 §2: Ingests raw captures. Delegates sanitization to DataSanitizer."""

    def __init__(self, sanitizer: "DataSanitizer", extraction_pipeline,
                 workspace_service, session_repo, queue):
        self.sanitizer = sanitizer          # Doc 10 §2: explicit DataSanitizer dep
        self.pipeline = extraction_pipeline
        self.workspace_service = workspace_service
        self.session_repo = session_repo
        self.queue = queue

    async def ingest(self, request: CaptureRequest) -> CaptureResult:
        # 1. Sensitive data check via DataSanitizer (delegates to Plan 02 sensitive_filter)
        check = self.sanitizer.check(f"{request.user_message}\n{request.ai_response}")
        if check.is_sensitive:
            return CaptureResult(capture_id=request.id, status="blocked",
                                 sensitive_data_detected=True)
        # 2. Workspace assignment (explicit or inferred via infer_workspace)
        ws_id = request.workspace_id or (
            await self.workspace_service.infer_workspace(
                request.user_message, request.ai_response, request.tab_url
            ))[0]
        # 3. Create/update session
        await self.session_repo.upsert_session(ws_id, request.session_id, request.platform)
        # 4. Queue for extraction worker (non-blocking)
        await self.queue.enqueue(ws_id, request)
        # 5. Return 202 Accepted
        return CaptureResult(capture_id=request.id, status="queued",
                             workspace_id=ws_id, sensitive_data_detected=False)

    async def get_status(self, capture_id: str) -> CaptureResult
```

### onboarding_service.py
```python
class OnboardingService:
    async def process_quick_add(self, workspace_id: str, goal: str,
                                 tech_stack: str, key_person: str) -> list[MemoryNode]
    async def suggest_workspace_name(self, description: str) -> str  # Via Phi-4
    async def retrospective_extraction(self, raw_text: str, platform: str,
                                        workspace_id: str) -> ExtractionResult
    async def log_event(self, event_type: str, metadata: dict = {})
    async def get_nudge(self) -> Optional[str]
```

---

## 7. WORKING MEMORY (backend/services/working_memory.py)

> **Gap fix — Doc 04 §3: Tier 1 Working Memory (in-memory, session-scoped)**

```python
from collections import OrderedDict

MAX_WORKING_MEMORY_SIZE = 50  # Doc 04 §3

class WorkingMemory:
    """
    Tier 1 memory — in-memory dict per session.
    NOT persisted to SQLite. TTL = session duration.
    Nodes promoted to Episodic/Semantic on session end or explicit save.
    """

    def __init__(self, workspace_id: str, session_id: str):
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.nodes: OrderedDict[str, MemoryNode] = OrderedDict()
        self.created_at = datetime.utcnow()

    def add(self, node: MemoryNode) -> None:
        """Add node to working memory. Evict least important if full."""
        if len(self.nodes) >= MAX_WORKING_MEMORY_SIZE:
            self._evict_least_important()
        node.tier = MemoryTier.WORKING
        self.nodes[node.id] = node

    def get(self, node_id: str) -> Optional[MemoryNode]:
        return self.nodes.get(node_id)

    def get_all(self) -> list[MemoryNode]:
        return list(self.nodes.values())

    def _evict_least_important(self):
        """Remove the node with lowest importance score."""
        if not self.nodes:
            return
        min_node = min(self.nodes.values(), key=lambda n: n.importance_score)
        del self.nodes[min_node.id]

    async def promote_to_episodic(self, node_id: str,
                                    graph_service: "GraphService") -> MemoryNode:
        """Promote working memory node to persistent episodic tier."""
        node = self.nodes.pop(node_id)
        node.tier = MemoryTier.EPISODIC
        committed = await graph_service.commit_node(
            self.workspace_id,
            ExtractionCandidate(
                node_type=node.node_type, content=node.content,
                structured_data=node.structured_data,
                confidence=node.extraction_confidence,
                source_pass="working_memory", evidence="promoted from session"
            ),
            self.session_id
        )
        return committed

    async def flush_on_session_end(self, graph_service: "GraphService"):
        """
        On session end: promote nodes that meet criteria.
        Criteria from Doc 04 §3:
        - Decisions always promote
        - Goals always promote
        - High importance (>0.7) promotes
        - Everything else discarded
        """
        promote_types = {NodeType.DECISION, NodeType.GOAL, NodeType.PROBLEM}
        for node_id, node in list(self.nodes.items()):
            if node.node_type in promote_types or node.importance_score > 0.7:
                await self.promote_to_episodic(node_id, graph_service)
        self.nodes.clear()


class WorkingMemoryManager:
    """Manages per-session working memory instances."""

    def __init__(self):
        self._sessions: dict[str, WorkingMemory] = {}

    def get_or_create(self, workspace_id: str, session_id: str) -> WorkingMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = WorkingMemory(workspace_id, session_id)
        return self._sessions[session_id]

    async def end_session(self, session_id: str, graph_service: "GraphService"):
        if session_id in self._sessions:
            await self._sessions[session_id].flush_on_session_end(graph_service)
            del self._sessions[session_id]
```

---

## 8. ENTITY DISAMBIGUATION (backend/services/conflict_service.py — addition)

> **Gap fix — Doc 05 §2 Type 6: Entity Disambiguation Conflict**

Add to `ConflictService`:

```python
    async def detect_entity_disambiguation(self, workspace_id: str,
                                            new_node: MemoryNode) -> list[ConflictCandidate]:
        """
        Doc 05 §2 Type 6: Same name refers to two different things.
        Example: 'Python' = language vs 'python.py' = file.
        Runs after commit, checks if entity name collides with existing node
        of different entity_type or different structured_data context.
        """
        if new_node.node_type != NodeType.ENTITY:
            return []

        entity_name = new_node.content.strip().lower()
        entity_type = new_node.structured_data.get("entity_type", "")

        # Find existing entities with same name but different type/context
        existing = await self.nodes.get_active(workspace_id, node_type=NodeType.ENTITY)
        conflicts = []
        for existing_node in existing:
            if existing_node.id == new_node.id:
                continue
            if existing_node.content.strip().lower() == entity_name:
                existing_type = existing_node.structured_data.get("entity_type", "")
                if existing_type and entity_type and existing_type != entity_type:
                    # Same name, different entity_type → disambiguation needed
                    conflicts.append(ConflictCandidate(
                        workspace_id=workspace_id,
                        node_a_id=existing_node.id,
                        node_b_id=new_node.id,
                        conflict_type=ConflictType.ENTITY_DISAMBIGUATION,
                        contradiction_score=0.90,
                        suggested_strategy=ConflictStrategy.USER_REVIEW,
                        auto_resolvable=False,  # Never auto-resolve disambiguation
                    ))
        return conflicts

    async def resolve_disambiguation(self, conflict_id: str,
                                      action: str,
                                      disambiguation_tags: dict = {}):
        """
        User resolves by either:
        - 'split': Create separate nodes with disambiguation tags
        - 'merge': Confirm they're the same entity
        - 'rename': Rename one to distinguish
        """
        conflict = await self.conflict_repo.get(conflict_id)
        if action == "split":
            # Add disambiguation tags to both nodes
            node_a = await self.nodes.get(conflict.node_a_id)
            node_b = await self.nodes.get(conflict.node_b_id)
            await self.nodes.update_metadata(node_a.id,
                structured_data={**node_a.structured_data,
                                 "disambiguation": disambiguation_tags.get("node_a", "")})
            await self.nodes.update_metadata(node_b.id,
                structured_data={**node_b.structured_data,
                                 "disambiguation": disambiguation_tags.get("node_b", "")})
        await self.conflict_repo.resolve(conflict_id, ResolutionEvent(
            conflict_id=conflict_id,
            strategy_used=ConflictStrategy.USER_REVIEW,
            status=ResolutionStatus.USER_RESOLVED,
            resolved_by="user"))
```

Also update the conflict type table in §3:

| Type | Example | Default Strategy |
|------|---------|-----------------|
| DIRECT_FACT | "uses PostgreSQL" vs "uses MongoDB" | TEMPORAL |
| PREFERENCE_DRIFT | "prefers tabs" vs "switched to spaces" | TEMPORAL |
| GOAL_CONFLICT | two mutually exclusive goals | USER_REVIEW |
| VERSION_FORK | same fact diverged in two sessions | CONFIDENCE_WEIGHTED |
| SCOPE_CONTRADICTION | "MVP includes X" vs "cut X from MVP" | TEMPORAL |
| LOGICAL_INCONSISTENCY | "deadline June 1" + "launch after July review" | LOGICAL_FLAG |
| ENTITY_DISAMBIGUATION | "Python" (language) vs "python.py" (file) | USER_REVIEW (never auto) |

---

## Files Summary

| File | Lines Est. |
|------|-----------|
| `backend/repositories/node_repo.py` | ~200 |
| `backend/repositories/edge_repo.py` | ~60 |
| `backend/repositories/workspace_repo.py` | ~80 |
| `backend/repositories/conflict_repo.py` | ~60 |
| `backend/repositories/pending_review_repo.py` | ~50 |
| `backend/repositories/session_repo.py` | ~50 |
| `backend/repositories/audit_repo.py` | ~80 |
| `backend/repositories/settings_repo.py` | ~40 |
| `backend/repositories/onboarding_repo.py` | ~40 |
| `backend/services/graph_service.py` | ~180 |
| `backend/services/conflict_service.py` | ~280 |
| `backend/services/decay_service.py` | ~80 |
| `backend/services/consolidation_service.py` | ~100 |
| `backend/services/retrieval_service.py` | ~180 |
| `backend/services/intent_service.py` | ~60 |
| `backend/services/workspace_service.py` | ~120 |
| `backend/services/embedding_service.py` | ~100 |
| `backend/services/capture_service.py` | ~80 |
| `backend/services/onboarding_service.py` | ~100 |
| `backend/services/working_memory.py` | ~100 |

**Total: ~22 files, ~2,040 lines.**

---

> **Next: Plan 04 — API Layer & Background Workers**
