# DOCUMENT 05 — CONFLICT RESOLUTION
## Contradiction Detection, Resolution Logic, Versioning
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. WHY THIS IS THE HARDEST PROBLEM

Conflict resolution is the most underspecified component in every AI memory system.

The naive approach: keep appending facts → eventually contradictions appear → AI gets confused.

The wrong approach: "last write wins" → you lose history, lose context, lose the WHY behind changes.

The right approach: **structured contradiction lifecycle with resolution tracking and temporal versioning.**

---

## 2. TYPES OF CONFLICTS

### Type 1: Direct Fact Contradiction
**Definition:** Two nodes assert opposite facts about the same entity.

**Example:**
- Node A: "Backend uses PostgreSQL"
- Node B: "Backend uses MongoDB"

**Resolution strategy:** Temporal — newer is current, older gets valid_until set.

---

### Type 2: Goal State Conflict
**Definition:** A goal is claimed to be both active and completed.

**Example:**
- Node A (GOAL): "Build depth estimation module" — status: ACTIVE
- Node B (EVENT): "Completed depth estimation module on June 5"

**Resolution strategy:** Event-triggered state change — mark goal COMPLETED.

---

### Type 3: Semantic Drift
**Definition:** The meaning of an entity has evolved but no explicit update was made.

**Example:**
- Node A: "Project targets Android only"
- Later text implies: "cross-platform deployment"
- No explicit decision node was created

**Resolution strategy:** Flag for user review with detected drift evidence.

---

### Type 4: Preference Contradiction
**Definition:** Two procedural memory nodes assert conflicting user preferences.

**Example:**
- Node A: "User prefers bullet points in responses"
- Node B: "User prefers dense prose, no bullets"

**Resolution strategy:** Confidence-weighted merge, flag most recent as dominant, archive older.

---

### Type 5: Relationship Conflict
**Definition:** Two edges assert incompatible relationships.

**Example:**
- Edge A: "Feature X DEPENDS_ON Feature Y"
- Edge B: "Feature Y DEPENDS_ON Feature X" (circular)

**Resolution strategy:** Flag as logical error, surface to user, do not auto-resolve.

---

### Type 6: Entity Disambiguation Conflict
**Definition:** Same name refers to two different things; system treated them as one.

**Example:**
- "Python" used to refer to both the language and a file named python.py
- Merged into one node incorrectly

**Resolution strategy:** NLP disambiguation check; if ambiguous, create separate nodes with disambiguation tag.

---

## 3. CONFLICT DETECTION PIPELINE

### 3.1 When Detection Runs
- After every new node commit
- During nightly consolidation pass
- When user triggers manual audit
- When retrieval returns conflicting nodes in same result set

### 3.2 Detection Methods

**Method A: Semantic Similarity Check**
When a new node is committed, check if any existing node in the same workspace has cosine similarity > 0.85 on the embedding vector AND is a different assertion.

```python
def detect_semantic_conflicts(new_node: MemoryNode, workspace_id: str) -> List[ConflictCandidate]:
    candidates = []
    
    # Get all active nodes of same type in workspace
    existing_nodes = self.store.get_active_nodes(
        workspace_id=workspace_id,
        node_type=new_node.node_type
    )
    
    for existing in existing_nodes:
        if existing.id == new_node.id:
            continue
        
        # Semantic similarity
        similarity = cosine_similarity(new_node.embedding_vector, existing.embedding_vector)
        
        if similarity > SEMANTIC_CONFLICT_THRESHOLD:  # 0.85
            # Check if they assert different things (not just similar)
            contradiction_score = self.contradiction_classifier.predict(
                new_node.content, existing.content
            )
            
            if contradiction_score > CONTRADICTION_THRESHOLD:  # 0.70
                candidates.append(ConflictCandidate(
                    node_a=existing,
                    node_b=new_node,
                    similarity=similarity,
                    contradiction_score=contradiction_score,
                    conflict_type=self._classify_conflict_type(existing, new_node)
                ))
    
    return candidates
```

**Method B: Entity + Attribute Hash Check**
For structured nodes (TechnicalFact), check if same entity has different attribute value.

```python
def detect_structural_conflicts(new_node: MemoryNode) -> List[ConflictCandidate]:
    if new_node.node_type != NodeType.TECHNICAL_FACT:
        return []
    
    entity = new_node.structured_data.get('entity')
    attribute = new_node.structured_data.get('attribute')
    new_value = new_node.structured_data.get('value')
    
    if not all([entity, attribute, new_value]):
        return []
    
    # Look for same entity + attribute with different value
    existing = self.store.query("""
        SELECT * FROM memory_nodes
        WHERE workspace_id = ?
        AND node_type = 'technical_fact'
        AND json_extract(structured_data, '$.entity') = ?
        AND json_extract(structured_data, '$.attribute') = ?
        AND json_extract(structured_data, '$.value') != ?
        AND status = 'ACTIVE'
        AND valid_until IS NULL
    """, new_node.workspace_id, entity, attribute, new_value)
    
    return [ConflictCandidate(node_a=e, node_b=new_node, 
                              conflict_type=ConflictType.DIRECT_FACT)
            for e in existing]
```

**Method C: Goal State Consistency Check**
When an event node is committed, check if it implies completion of an active goal.

```python
def detect_goal_state_conflicts(new_event: MemoryNode) -> List[ConflictCandidate]:
    if new_event.node_type != NodeType.EVENT:
        return []
    
    completion_phrases = ["completed", "finished", "shipped", "launched", "deployed", "done"]
    
    if not any(phrase in new_event.content.lower() for phrase in completion_phrases):
        return []
    
    # Extract subject of completion
    subject = self.ner.extract_subject(new_event.content)
    
    # Find active goals matching subject
    matching_goals = self.store.semantic_search(
        workspace_id=new_event.workspace_id,
        query=subject,
        node_type=NodeType.GOAL,
        filter={"status": "ACTIVE"},
        top_k=3
    )
    
    candidates = []
    for goal in matching_goals:
        if cosine_similarity(new_event.embedding, goal.embedding) > 0.75:
            candidates.append(ConflictCandidate(
                node_a=goal,
                node_b=new_event,
                conflict_type=ConflictType.GOAL_STATE
            ))
    
    return candidates
```

---

## 4. CONFLICT RESOLUTION STRATEGIES

### Strategy 1: Temporal Resolution (Default for Direct Facts)

**When to use:** Two nodes assert contradictory facts; newer one is likely correct.

**Conditions for auto-resolve:**
- Both nodes are same type (TECHNICAL_FACT, GOAL, etc.)
- Time difference > configured threshold (default: 24 hours)
- Neither node is user-verified

**Algorithm:**
```python
def resolve_temporal(conflict: ConflictCandidate) -> ResolutionResult:
    older = conflict.node_a if conflict.node_a.created_at < conflict.node_b.created_at else conflict.node_b
    newer = conflict.node_b if older == conflict.node_a else conflict.node_a
    
    # Archive older version
    older.valid_until = newer.valid_from
    older.status = NodeStatus.SUPERSEDED
    
    # Create an edge: newer SUPERSEDES older
    edge = MemoryEdge(
        source_node_id=newer.id,
        target_node_id=older.id,
        edge_type=EdgeType.SUPERSEDES,
        label=f"Updated from: {older.content[:50]}..."
    )
    
    # Log resolution
    resolution = ResolutionEvent(
        conflict_id=conflict.id,
        strategy=ResolutionStrategy.TEMPORAL,
        winning_node_id=newer.id,
        archived_node_id=older.id,
        auto_resolved=True,
        resolved_at=datetime.utcnow()
    )
    
    return ResolutionResult(
        resolved=True,
        winning_node=newer,
        archived_nodes=[older],
        resolution_event=resolution,
        edge=edge
    )
```

---

### Strategy 2: User Review (For High-Stakes Conflicts)

**When to use:**
- Either node is user-verified
- Confidence scores are close (within 0.1)
- Conflict type is semantic drift or preference contradiction
- Node importance > 0.8

**Process:**
1. Create `PendingReview` record with both conflicting nodes
2. Show in Memory Audit UI under "Conflicts" tab
3. Present user with both options + evidence
4. User selects winner or edits to create merged version
5. System executes resolution based on user choice

**UI Presentation:**
```
⚠️  CONFLICT DETECTED

Topic: Backend Database

Node A (June 1):   "Backend uses PostgreSQL"
Node B (June 15):  "Backend uses MongoDB"

What happened?
○ We switched from PostgreSQL to MongoDB on June 15
○ These are different services (not a conflict)
○ Node A is correct, Node B is wrong
○ Node B is correct, Node A is wrong
○ Write my own resolution: [text field]

[ Resolve ] [ Skip for now ]
```

---

### Strategy 3: Confidence-Weighted Merge (For Preference Nodes)

**When to use:** Two preference nodes are contradictory; need to synthesize.

**Algorithm:**
```python
def resolve_preference_merge(conflict: ConflictCandidate) -> ResolutionResult:
    node_a = conflict.node_a
    node_b = conflict.node_b
    
    # Weight by: confidence × recency × reinforcement_count
    weight_a = (node_a.extraction_confidence * 
                node_a.reinforcement_count * 
                recency_weight(node_a.last_accessed))
    
    weight_b = (node_b.extraction_confidence * 
                node_b.reinforcement_count * 
                recency_weight(node_b.last_accessed))
    
    if weight_a > weight_b * 1.5:
        # A is clearly dominant
        winner = node_a
        loser = node_b
        auto_resolve = True
    elif weight_b > weight_a * 1.5:
        winner = node_b
        loser = node_a
        auto_resolve = True
    else:
        # Too close to call — queue for user review
        return ResolutionResult(resolved=False, needs_review=True)
    
    # Archive loser
    loser.status = NodeStatus.SUPERSEDED
    loser.valid_until = datetime.utcnow()
    
    # Boost winner
    winner.importance_score = min(1.0, winner.importance_score + 0.1)
    winner.reinforcement_count += 1
    
    return ResolutionResult(resolved=True, winning_node=winner, 
                           auto_resolved=auto_resolve)
```

---

### Strategy 4: Logical Error Flagging (For Circular Dependencies)

**When to use:** Relationship conflict creates logical impossibility.

**Process:**
- Do not auto-resolve
- Flag both edges as `CONFLICTED`
- Add to error log
- Surface prominently in audit UI
- Block retrieval from returning both edges simultaneously

---

## 5. CONFLICT RESOLUTION DECISION TREE

```
New node committed
       ↓
Run conflict detection
       ↓
Conflicts found?
  ├── NO → Commit normally
  └── YES
       ↓
       Classify conflict type
       ↓
  ┌────────────────────────────────────────┐
  │                                        │
  ▼                                        ▼
DIRECT_FACT / GOAL_STATE           SEMANTIC_DRIFT /
                                   PREFERENCE / LOGICAL_ERROR
  ↓                                        ↓
Either node user-verified?         Flag for user review
  ├── YES → User review queue
  └── NO
       ↓
  Time diff > 24h AND
  confidence gap > 0.1?
  ├── YES → Temporal resolution (auto)
  └── NO → User review queue
```

---

## 6. RESOLUTION EVENT LOG

Every conflict resolution creates an immutable audit record:

```python
@dataclass
class ResolutionEvent:
    id: str
    workspace_id: str
    conflict_id: str
    
    conflict_type: ConflictType
    strategy_used: ResolutionStrategy
    
    winning_node_id: str
    archived_node_ids: List[str]
    
    auto_resolved: bool
    resolved_by_user: Optional[str]  # User ID if manual
    
    resolved_at: datetime
    
    # For audit trail
    evidence: str                    # Why this resolution was chosen
    confidence: float                # System's confidence in resolution
```

This log is:
- Never deleted (even if node is deleted, resolution record persists)
- Visible in audit UI under "Resolution History"
- Exportable as JSON

---

## 7. ANTI-PATTERNS TO AVOID

### ❌ Last Write Wins (No Versioning)
**Problem:** Silently loses historical facts. No ability to understand how workspace evolved.

### ❌ Keep All Conflicting Nodes Active
**Problem:** Retrieval returns contradictory facts. AI gets confused.

### ❌ Always Ask User to Resolve
**Problem:** Cognitive overhead destroys user experience. Auto-resolve what's obvious.

### ❌ Delete Old Facts
**Problem:** Loses the historical record. "What did we decide on June 3?" becomes unanswerable.

### ✅ Correct Approach Summary
- Version everything (old facts become superseded, not deleted)
- Auto-resolve when temporal evidence is clear
- Queue for review when ambiguous
- Log every resolution with evidence
- Never lose the "why" of a change

---

## 8. CONFLICT METRICS TO TRACK

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Auto-resolve rate | > 70% | < 50% |
| User review queue depth | < 10 items | > 25 items |
| False positive conflict rate | < 15% | > 25% |
| Conflict resolution latency | < 100ms | > 500ms |
| Unresolved conflict age | < 7 days | > 14 days |
