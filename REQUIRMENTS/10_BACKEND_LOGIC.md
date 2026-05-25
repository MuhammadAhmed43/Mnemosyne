# DOCUMENT 10 — BACKEND LOGIC
## Core Business Logic, Service Layer, Orchestration
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. SERVICE ARCHITECTURE

The backend is organized as a **service layer** — no business logic in route handlers.

```
FastAPI Routes
     ↓
Service Layer (business logic)
     ↓
Repository Layer (database access)
     ↓
Storage (SQLite + Qdrant)
```

### Service Classes

| Service | Responsibility |
|---------|---------------|
| `CaptureService` | Receive captures, sanitize, route to queue |
| `ExtractionService` | Run extraction pipeline, score candidates |
| `GraphService` | CRUD on knowledge graph, traversal |
| `RetrievalService` | Multi-source retrieval, context construction |
| `ConflictService` | Detect and resolve conflicts |
| `DecayService` | Schedule and apply memory decay |
| `WorkspaceService` | Workspace lifecycle management |
| `EmbeddingService` | Generate and manage vector embeddings |

---

## 2. CAPTURE SERVICE

```python
class CaptureService:
    def __init__(
        self,
        sanitizer: DataSanitizer,
        workspace_service: WorkspaceService,
        extraction_queue: ExtractionQueue
    ):
        self.sanitizer = sanitizer
        self.workspace_service = workspace_service
        self.extraction_queue = extraction_queue
    
    async def ingest(self, capture: CaptureRequest) -> CaptureResult:
        # 1. Sanitize
        sanitized = self.sanitizer.process(capture)
        if sanitized.was_blocked:
            return CaptureResult(status='blocked', reason=sanitized.block_reason)
        
        # 2. Trivial check
        if self._is_trivial(sanitized.user_message, sanitized.ai_response):
            return CaptureResult(status='skipped', reason='trivial')
        
        # 3. Workspace resolution
        workspace_id = capture.workspace_id
        if not workspace_id:
            workspace_id = await self.workspace_service.infer_workspace(
                capture.user_message,
                capture.ai_response,
                capture.tab_url
            )
        
        # 4. Queue for extraction
        capture_record = CaptureRecord(
            id=generate_id(),
            workspace_id=workspace_id,
            user_message=sanitized.user_message,
            ai_response=sanitized.ai_response,
            platform=capture.platform,
            session_id=capture.session_id,
            timestamp=capture.timestamp,
            status='queued'
        )
        
        await self.extraction_queue.push(capture_record)
        
        return CaptureResult(
            status='queued',
            capture_id=capture_record.id,
            workspace_id=workspace_id
        )
    
    def _is_trivial(self, user_msg: str, ai_msg: str) -> bool:
        combined = (user_msg + ai_msg).strip()
        # Too short to contain useful information
        if len(combined) < 50:
            return True
        # Pure code with no natural language
        if self._is_pure_code(combined):
            return True
        # Conversational pleasantries
        trivial_patterns = ['thank you', 'thanks', 'hello', 'hi there', 'okay']
        if combined.lower() in trivial_patterns:
            return True
        return False
```

---

## 3. RETRIEVAL SERVICE

**This is the most latency-critical service. Target: < 300ms end-to-end.**

```python
class RetrievalService:
    def __init__(
        self,
        graph_service: GraphService,
        vector_store: VectorStore,
        intent_analyzer: IntentAnalyzer
    ):
        self.graph = graph_service
        self.vectors = vector_store
        self.intent = intent_analyzer
    
    async def get_context(
        self, 
        workspace_id: str,
        token_budget: int = 2000,
        intent_hint: Optional[str] = None,
        platform: str = 'claude'
    ) -> ContextResult:
        
        # 1. Analyze intent (what is user likely about to do?)
        intent = await self.intent.analyze(
            workspace_id=workspace_id,
            hint=intent_hint
        )
        
        # 2. Run retrieval sources in parallel
        results = await asyncio.gather(
            self._retrieve_active_goals(workspace_id),
            self._retrieve_recent_decisions(workspace_id),
            self._retrieve_open_problems(workspace_id),
            self._retrieve_semantic_relevant(workspace_id, intent),
            self._retrieve_high_importance(workspace_id),
            return_exceptions=True
        )
        
        # 3. Merge and deduplicate
        all_nodes = []
        for result in results:
            if not isinstance(result, Exception):
                all_nodes.extend(result)
        
        unique_nodes = self._deduplicate(all_nodes)
        
        # 4. Rank
        ranked_nodes = self._rank_for_context(unique_nodes, intent)
        
        # 5. Budget allocation
        selected_nodes = self._fit_to_token_budget(ranked_nodes, token_budget)
        
        # 6. Construct context string
        context_string = self._build_context_string(
            workspace_id=workspace_id,
            nodes=selected_nodes,
            platform=platform
        )
        
        # 7. Update access timestamps
        await self._update_access_timestamps([n.id for n in selected_nodes])
        
        return ContextResult(
            workspace_id=workspace_id,
            context_string=context_string,
            nodes_included=selected_nodes,
            token_count=self._count_tokens(context_string)
        )
    
    async def _retrieve_active_goals(self, workspace_id: str) -> List[MemoryNode]:
        """Always include active goals — highest priority."""
        return await self.graph.get_nodes(
            workspace_id=workspace_id,
            node_type=NodeType.GOAL,
            filter={'status': 'ACTIVE'},
            sort_by='importance_score',
            limit=5
        )
    
    async def _retrieve_recent_decisions(self, workspace_id: str) -> List[MemoryNode]:
        """Recent decisions (last 14 days) are always relevant."""
        cutoff = datetime.utcnow() - timedelta(days=14)
        return await self.graph.get_nodes(
            workspace_id=workspace_id,
            node_type=NodeType.DECISION,
            filter={'created_at_after': cutoff},
            sort_by='created_at',
            limit=5
        )
    
    async def _retrieve_open_problems(self, workspace_id: str) -> List[MemoryNode]:
        """Open blockers are always surfaced."""
        return await self.graph.get_nodes(
            workspace_id=workspace_id,
            node_type=NodeType.PROBLEM,
            filter={'status': 'OPEN'},
            sort_by='importance_score',
            limit=3
        )
    
    async def _retrieve_semantic_relevant(
        self, workspace_id: str, intent: Intent
    ) -> List[MemoryNode]:
        """Semantic search based on inferred intent."""
        if not intent.query_vector:
            return []
        
        return await self.vectors.search(
            workspace_id=workspace_id,
            query_vector=intent.query_vector,
            top_k=10,
            filter={'status': 'ACTIVE'}
        )
    
    def _rank_for_context(
        self, nodes: List[MemoryNode], intent: Intent
    ) -> List[MemoryNode]:
        """Score and sort nodes for context inclusion."""
        
        def score(node: MemoryNode) -> float:
            base = node.importance_score
            
            # Type priority (goals and decisions always first)
            type_priority = {
                NodeType.GOAL: 1.3,
                NodeType.DECISION: 1.2,
                NodeType.PROBLEM: 1.15,
                NodeType.TECHNICAL_FACT: 1.0,
                NodeType.PREFERENCE: 0.9,
                NodeType.ENTITY: 0.8,
                NodeType.EVENT: 0.7,
                NodeType.TASK: 0.9,
            }
            base *= type_priority.get(node.node_type, 1.0)
            
            # Recency boost
            days_old = (datetime.utcnow() - node.updated_at).days
            recency = max(0.5, 1.0 - (days_old / 90))  # Decays over 90 days
            base *= recency
            
            # Intent relevance (if semantic score available)
            if hasattr(node, '_semantic_score'):
                base *= (0.7 + 0.3 * node._semantic_score)
            
            # User-verified nodes get a boost
            if node.user_verified:
                base *= 1.2
            
            return min(1.0, base)
        
        nodes.sort(key=score, reverse=True)
        return nodes
    
    def _build_context_string(
        self, workspace_id: str, nodes: List[MemoryNode], platform: str
    ) -> str:
        """Build the final context string for injection."""
        
        workspace = self.workspace_service.get(workspace_id)
        
        sections = {
            NodeType.GOAL: [],
            NodeType.DECISION: [],
            NodeType.PROBLEM: [],
            NodeType.TECHNICAL_FACT: [],
            NodeType.ENTITY: [],
            NodeType.PREFERENCE: [],
        }
        
        for node in nodes:
            sections[node.node_type].append(node)
        
        lines = [f"[MNEMOSYNE — Workspace: {workspace.name}]", ""]
        
        if sections[NodeType.GOAL]:
            lines.append("Current Goals:")
            for node in sections[NodeType.GOAL]:
                priority = node.structured_data.get('priority', '')
                deadline = node.structured_data.get('deadline', '')
                suffix = f" [{priority}]" if priority else ""
                if deadline:
                    suffix += f" · Due: {deadline}"
                lines.append(f"• {node.content}{suffix}")
            lines.append("")
        
        if sections[NodeType.DECISION]:
            lines.append("Recent Decisions:")
            for node in sections[NodeType.DECISION]:
                date = node.created_at.strftime('%b %d')
                rationale = node.structured_data.get('rationale', '')
                reason = f" — {rationale}" if rationale else ""
                lines.append(f"• {node.content} ({date}){reason}")
            lines.append("")
        
        if sections[NodeType.PROBLEM]:
            lines.append("Open Problems:")
            for node in sections[NodeType.PROBLEM]:
                lines.append(f"• {node.content}")
            lines.append("")
        
        if sections[NodeType.TECHNICAL_FACT]:
            # Group tech facts by category
            by_category = {}
            for node in sections[NodeType.TECHNICAL_FACT]:
                cat = node.structured_data.get('category', 'other')
                by_category.setdefault(cat, []).append(node.structured_data.get('value', node.content))
            
            lines.append("Technical Stack:")
            for cat, values in by_category.items():
                lines.append(f"• {cat.title()}: {', '.join(values)}")
            lines.append("")
        
        if sections[NodeType.PREFERENCE]:
            lines.append("Working Preferences:")
            for node in sections[NodeType.PREFERENCE]:
                lines.append(f"• {node.content}")
            lines.append("")
        
        if sections[NodeType.ENTITY]:
            people = [n for n in sections[NodeType.ENTITY] 
                     if n.structured_data.get('entity_class') == 'PERSON']
            if people:
                lines.append("Key People:")
                for node in people:
                    role = node.structured_data.get('role', '')
                    role_str = f" ({role})" if role else ""
                    lines.append(f"• {node.content}{role_str}")
                lines.append("")
        
        return "\n".join(lines)
```

---

## 4. DECAY SERVICE

```python
class DecayService:
    def __init__(self, graph_service: GraphService):
        self.graph = graph_service
    
    async def run_decay_cycle(self, workspace_id: str) -> DecayCycleResult:
        """Run every 6 hours per workspace."""
        
        all_active_nodes = await self.graph.get_all_active(workspace_id)
        
        to_archive = []
        to_prune = []
        to_update = []
        
        for node in all_active_nodes:
            if node.is_permanent:
                continue  # Never decay permanent nodes
            
            retention = self._compute_retention(node)
            
            if retention < 0.2:
                to_prune.append(node)
            elif retention < 0.4:
                to_archive.append(node)
            else:
                # Update importance score based on decay
                node.importance_score = max(0.1, node.importance_score * (1 - node.decay_rate * 0.01))
                to_update.append(node)
        
        # Execute changes
        await self.graph.archive_nodes([n.id for n in to_archive])
        await self.graph.move_to_cold_storage([n.id for n in to_prune])
        await self.graph.update_importance_scores(
            {n.id: n.importance_score for n in to_update}
        )
        
        return DecayCycleResult(
            archived=len(to_archive),
            pruned=len(to_prune),
            updated=len(to_update)
        )
    
    def _compute_retention(self, node: MemoryNode) -> float:
        days_since_access = (datetime.utcnow() - (node.last_accessed or node.created_at)).days
        
        recency_factor = math.exp(-node.decay_rate * days_since_access)
        reinforcement_bonus = 1 + (0.1 * min(node.reinforcement_count, 10))
        workspace_relevance = self._get_workspace_relevance(node.workspace_id)
        
        return node.importance_score * recency_factor * reinforcement_bonus * workspace_relevance
```

---

## 5. CONSOLIDATION SERVICE

Runs daily. Finds and merges duplicate/near-duplicate nodes.

```python
class ConsolidationService:
    async def run_consolidation(self, workspace_id: str) -> ConsolidationResult:
        """
        Find semantically similar nodes that should be merged.
        Different from conflict detection — these aren't contradictions,
        they're just saying the same thing twice.
        """
        
        active_nodes = await self.graph.get_all_active(workspace_id)
        
        # Build similarity matrix (batched for performance)
        duplicates = await self._find_near_duplicates(active_nodes)
        
        merged = 0
        for (node_a, node_b, similarity) in duplicates:
            if similarity > MERGE_THRESHOLD:  # 0.92
                # Keep the higher-importance node, merge metadata
                winner, loser = (
                    (node_a, node_b) if node_a.importance_score >= node_b.importance_score
                    else (node_b, node_a)
                )
                
                # Merge reinforcement counts
                winner.reinforcement_count += loser.reinforcement_count
                winner.importance_score = min(1.0, winner.importance_score + 0.05)
                
                # Archive loser with reference to winner
                await self.graph.archive_node(
                    loser.id,
                    reason=f"Merged into {winner.id} (similarity: {similarity:.2f})"
                )
                
                merged += 1
        
        return ConsolidationResult(merged=merged, checked=len(active_nodes))
```

---

## 6. INTENT ANALYZER

```python
class IntentAnalyzer:
    """
    Infers what the user is likely about to do in the current session.
    Used to improve retrieval relevance.
    """
    
    async def analyze(
        self, workspace_id: str, hint: Optional[str] = None
    ) -> Intent:
        
        # 1. Tab URL signals
        # 2. Recent session history in workspace
        # 3. Time-of-day patterns
        # 4. User-provided hint
        
        signals = []
        
        if hint:
            signals.append(await self.embed(hint))
        
        # Get recent session activity
        recent_sessions = await self.graph.get_recent_sessions(
            workspace_id, limit=3
        )
        if recent_sessions:
            recent_content = " ".join([s.summary for s in recent_sessions])
            signals.append(await self.embed(recent_content))
        
        # Active goals are always relevant intent signals
        active_goals = await self.graph.get_nodes(
            workspace_id, node_type=NodeType.GOAL,
            filter={'status': 'ACTIVE'}, limit=3
        )
        if active_goals:
            goal_text = " ".join([g.content for g in active_goals])
            signals.append(await self.embed(goal_text))
        
        if signals:
            # Average the signal embeddings
            query_vector = np.mean(signals, axis=0).tolist()
        else:
            query_vector = None
        
        return Intent(
            query_vector=query_vector,
            primary_signal=hint or (active_goals[0].content if active_goals else None)
        )
```

---

## 7. BACKGROUND WORKERS

```python
# workers.py

async def extraction_worker(queue: ExtractionQueue, extraction_service: ExtractionService):
    """Continuously process capture queue."""
    while True:
        try:
            capture = await queue.get(timeout=5)
            if capture:
                result = await extraction_service.process(capture)
                logger.info(
                    f"Extracted {len(result.auto_committed)} nodes, "
                    f"{len(result.pending_review)} pending"
                )
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Extraction worker error: {e}")
            await asyncio.sleep(1)

async def decay_worker(decay_service: DecayService, workspace_service: WorkspaceService):
    """Run decay cycle every 6 hours."""
    while True:
        await asyncio.sleep(6 * 3600)  # 6 hours
        active_workspaces = await workspace_service.get_active()
        for workspace in active_workspaces:
            try:
                result = await decay_service.run_decay_cycle(workspace.id)
                logger.info(f"Decay cycle for {workspace.name}: {result}")
            except Exception as e:
                logger.error(f"Decay worker error for {workspace.id}: {e}")

async def consolidation_worker(consolidation_service: ConsolidationService, workspace_service: WorkspaceService):
    """Run consolidation daily at 3am."""
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=3, minute=0, second=0) + timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        
        active_workspaces = await workspace_service.get_active()
        for workspace in active_workspaces:
            await consolidation_service.run_consolidation(workspace.id)

async def pending_review_cleanup_worker(review_service: ReviewService):
    """Expire old pending review items daily."""
    while True:
        await asyncio.sleep(24 * 3600)
        expired = await review_service.expire_old_pending()
        logger.info(f"Expired {expired} pending review items")
```

---

## 8. WORKSPACE INFERENCE

When no workspace is selected, the system must infer:

```python
async def infer_workspace(
    self,
    user_message: str,
    ai_response: str,
    tab_url: str
) -> str:
    """Returns workspace_id or NEEDS_NEW_WORKSPACE signal."""
    
    text = f"{user_message} {ai_response}"
    text_embedding = await self.embedding_service.embed(text)
    
    active_workspaces = await self.get_active_workspaces()
    
    if not active_workspaces:
        return NEEDS_NEW_WORKSPACE
    
    scores = {}
    for workspace in active_workspaces:
        if workspace.summary_embedding_id:
            workspace_embedding = await self.vector_store.get_embedding(
                workspace.summary_embedding_id
            )
            similarity = cosine_similarity(text_embedding, workspace_embedding)
            scores[workspace.id] = similarity
    
    if not scores:
        return NEEDS_NEW_WORKSPACE
    
    best_id = max(scores, key=scores.get)
    best_score = scores[best_id]
    
    # If best match is below threshold, suggest new workspace
    if best_score < 0.55:
        return NEEDS_NEW_WORKSPACE
    
    return best_id
```

---

## 9. STARTUP & LIFECYCLE

```python
# main.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Mnemosyne starting up...")
    
    await db_manager.initialize()           # Open all workspace DBs
    await vector_store.initialize()         # Start Qdrant local
    await embedding_service.initialize()    # Load embedding model
    
    # Start background workers
    asyncio.create_task(extraction_worker(capture_queue, extraction_service))
    asyncio.create_task(decay_worker(decay_service, workspace_service))
    asyncio.create_task(consolidation_worker(consolidation_service, workspace_service))
    asyncio.create_task(pending_review_cleanup_worker(review_service))
    
    logger.info("Mnemosyne ready on :7432")
    
    yield  # App is running
    
    # Shutdown
    logger.info("Mnemosyne shutting down...")
    await db_manager.close_all()
    await vector_store.shutdown()

app = FastAPI(lifespan=lifespan)
```
