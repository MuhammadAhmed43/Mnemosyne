# DOCUMENT 06 — COGNITIVE EXTRACTION PIPELINE
## How Raw Conversations Become Structured Memory
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. EXTRACTION PHILOSOPHY

**The single most important design principle:**

> Never store what was said. Store what it means.

A 3,000-word conversation about a hackathon should produce ~15 structured memory nodes, not 3,000 words of text.

The extraction pipeline is the intelligence of Mnemosyne. If this is bad, everything else fails.

---

## 2. THREE-PASS EXTRACTION ARCHITECTURE

Extraction uses **three passes in sequence**, each building on the previous:

```
RAW TEXT
   ↓
PASS 1: RULE-BASED (Fast, High Precision)
   ↓
PASS 2: NER + LINGUISTIC (Medium, High Recall)
   ↓
PASS 3: LLM-BASED (Slow, High Understanding)
   ↓
MERGE + CONFIDENCE SCORING
   ↓
STRUCTURED CANDIDATES
```

### Why Three Passes?

| Pass | Speed | Precision | Recall | Use For |
|------|-------|-----------|--------|---------|
| Rule-based | < 10ms | Very High | Low | Obvious patterns (tech stack, dates, keywords) |
| NER/Linguistic | < 100ms | High | Medium | Entities, relationships, sentence structure |
| LLM-based | < 500ms | Medium | High | Goals, decisions, implicit preferences |

Running all three catches what each individual pass misses, without requiring expensive LLM calls for everything.

---

## 3. PASS 1 — RULE-BASED EXTRACTION

### 3.1 Technology Stack Patterns

```python
TECH_PATTERNS = {
    'database': r'\b(PostgreSQL|MySQL|MongoDB|Redis|SQLite|DynamoDB|Cassandra|Supabase)\b',
    'language': r'\b(Python|TypeScript|JavaScript|Rust|Go|Java|Kotlin|Swift)\b',
    'framework': r'\b(FastAPI|Django|Flask|Express|Next\.js|React|Vue|Angular|LangChain|LangGraph)\b',
    'cloud': r'\b(AWS|GCP|Azure|Vercel|Railway|Render|Fly\.io)\b',
    'model': r'\b(GPT-4|GPT-5|Claude|Gemini|Llama|Mistral|Phi-4|Qwen)\b',
    'tool': r'\b(Docker|Kubernetes|GitHub Actions|Terraform|Ansible)\b'
}

def extract_tech_facts(text: str) -> List[ExtractionCandidate]:
    candidates = []
    for category, pattern in TECH_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in set(matches):
            candidates.append(ExtractionCandidate(
                node_type=NodeType.TECHNICAL_FACT,
                content=f"Using {match}",
                structured_data={
                    'entity': match,
                    'category': category,
                    'attribute': 'technology',
                    'value': match
                },
                confidence=0.90,
                extraction_pass='rule_based',
                source_text=find_context(text, match)
            ))
    return candidates
```

### 3.2 Decision Trigger Patterns

```python
DECISION_TRIGGERS = [
    r"(?:we |I |team )(?:decided|chose|picked|went with|selected|opted for) (.+)",
    r"(?:decision|choice|conclusion)(?:\s*:|\s+is|\s+was) (.+)",
    r"(?:we're|we are) (?:going with|using|sticking with) (.+)",
    r"(?:dropped|removed|cut|deprecated|killed) (.+) (?:from|because|since)",
    r"(?:won't|will not|no longer|not going to) (?:use|build|include) (.+)",
]

RATIONALE_TRIGGERS = [
    r"because (.+)",
    r"reason(?:\s*:|\s+is|\s+was) (.+)",
    r"since (.+)",
    r"due to (.+)",
    r"to (?:avoid|prevent|reduce|improve) (.+)",
]
```

### 3.3 Goal / Task Patterns

```python
GOAL_TRIGGERS = [
    r"(?:need to|have to|must|should|want to|going to|planning to) (.+)",
    r"(?:goal|objective|aim|target)(?:\s*:|\s+is|\s+to) (.+)",
    r"by (?:end of|Friday|Sunday|next week|tomorrow|Monday) (.+)",
    r"(?:deadline|due|ship|launch|release) (?:is |on |by )?(.+)",
]

COMPLETION_TRIGGERS = [
    r"(?:completed|finished|shipped|launched|deployed|done with|wrapped up) (.+)",
    r"(.+) (?:is done|is complete|is finished|is shipped|is live)",
]
```

---

## 4. PASS 2 — NER + LINGUISTIC EXTRACTION

### 4.1 Tools Used
- **spaCy** (en_core_web_sm) — NER, dependency parsing, coreference
- Custom entity rulers for tech domain

### 4.2 Entity Types Extracted

```python
ENTITY_LABELS = {
    'PERSON': 'Human collaborator or stakeholder',
    'ORG': 'Company, team, or institution',
    'PRODUCT': 'Software product or service',
    'TECH': 'Custom: technology, tool, framework',
    'CONCEPT': 'Abstract concept important to workspace',
    'DATE': 'Temporal reference',
    'MONEY': 'Budget or financial reference',
}
```

### 4.3 Relationship Extraction (Dependency Parsing)

```python
def extract_relationships(doc: spacy.Doc) -> List[ExtractionCandidate]:
    relationships = []
    
    for token in doc:
        # Subject-Verb-Object patterns
        if token.dep_ == 'ROOT':
            subject = [t for t in token.lefts if t.dep_ in ('nsubj', 'nsubjpass')]
            obj = [t for t in token.rights if t.dep_ in ('dobj', 'attr', 'pobj')]
            
            if subject and obj:
                rel_type = classify_relationship(token.lemma_)
                if rel_type:
                    relationships.append(ExtractionCandidate(
                        node_type=NodeType.RELATIONSHIP,
                        content=f"{subject[0].text} {rel_type} {obj[0].text}",
                        structured_data={
                            'source': subject[0].text,
                            'relation': rel_type,
                            'target': obj[0].text,
                            'verb': token.text
                        },
                        confidence=0.75
                    ))
    
    return relationships

RELATIONSHIP_VERB_MAP = {
    'use': 'USES', 'depend': 'DEPENDS_ON', 'block': 'BLOCKS',
    'require': 'REQUIRES', 'integrate': 'INTEGRATES_WITH',
    'replace': 'REPLACES', 'extend': 'EXTENDS', 'include': 'INCLUDES'
}
```

---

## 5. PASS 3 — LLM-BASED EXTRACTION

### 5.1 When to Use LLM Pass

LLM extraction is ONLY triggered when:
- Rule-based + NER passes didn't find any goals or decisions
- Conversation turn is > 3 sentences
- Text contains first-person statements about plans/preferences
- Text discusses multiple complex topics

**This is important for cost/speed control.** Not every turn needs LLM extraction.

### 5.2 Model Used

- **Local (default):** Phi-4 mini via Ollama
- **Fallback (if local unavailable):** Claude API (with user permission)
- **Context window used:** 4096 tokens max

### 5.3 Extraction Prompt

```python
EXTRACTION_SYSTEM_PROMPT = """
You are a cognitive extraction engine. Your job is to extract structured 
memory from AI conversation snippets.

Extract ONLY what is explicitly stated or very strongly implied.
Do NOT infer things that aren't there.
Do NOT extract generic or obvious facts (e.g., "user is having a conversation").

Return ONLY valid JSON. No preamble, no explanation.

Output format:
{
  "goals": [
    {
      "content": "exact goal statement",
      "priority": "HIGH|MEDIUM|LOW",
      "deadline": "ISO date or null",
      "status": "ACTIVE|COMPLETED|ABANDONED"
    }
  ],
  "decisions": [
    {
      "content": "what was decided",
      "rationale": "why (if stated)",
      "reversible": true|false
    }
  ],
  "preferences": [
    {
      "content": "behavioral preference",
      "domain": "communication|technical|workflow|other"
    }
  ],
  "open_problems": [
    {
      "content": "unresolved issue",
      "severity": "BLOCKING|IMPORTANT|MINOR"
    }
  ],
  "technical_facts": [
    {
      "entity": "what",
      "attribute": "property",
      "value": "current value"
    }
  ]
}
"""

EXTRACTION_USER_PROMPT = """
Extract structured memory from this conversation turn:

USER: {user_message}

AI: {ai_response}

Workspace context (for disambiguation): {workspace_summary}
"""
```

### 5.4 LLM Response Validation

```python
def validate_llm_extraction(raw_response: str) -> ExtractedData:
    try:
        # Clean response (strip markdown code fences)
        cleaned = re.sub(r'```(?:json)?|```', '', raw_response).strip()
        data = json.loads(cleaned)
        
        validated = ExtractedData()
        
        # Validate goals
        for goal in data.get('goals', []):
            if len(goal.get('content', '')) > 10:  # Non-trivial content
                validated.goals.append(ValidatedGoal(
                    content=goal['content'][:500],  # Cap length
                    priority=goal.get('priority', 'MEDIUM'),
                    confidence=0.75  # LLM extractions get lower base confidence
                ))
        
        # Similar validation for other types...
        
        return validated
    
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM extraction validation failed: {e}")
        return ExtractedData()  # Return empty, don't crash
```

---

## 6. MERGE + CONFIDENCE SCORING

After all three passes, merge results:

```python
def merge_extraction_passes(
    rule_based: List[ExtractionCandidate],
    ner_based: List[ExtractionCandidate],
    llm_based: List[ExtractionCandidate]
) -> List[ExtractionCandidate]:
    
    all_candidates = rule_based + ner_based + llm_based
    merged = {}
    
    for candidate in all_candidates:
        # Create a signature for deduplication
        sig = create_semantic_signature(candidate)
        
        if sig in merged:
            existing = merged[sig]
            # Boost confidence when multiple passes agree
            existing.confidence = min(1.0, existing.confidence + 0.10)
            existing.corroborated_by.append(candidate.extraction_pass)
        else:
            merged[sig] = candidate
    
    return list(merged.values())

def compute_final_confidence(candidate: ExtractionCandidate) -> float:
    base = candidate.confidence
    
    # Corroboration boost (multiple passes found same thing)
    corroboration_boost = len(candidate.corroborated_by) * 0.08
    
    # Context boost (if workspace context corroborates)
    context_boost = 0.05 if workspace_context_corroborates(candidate) else 0
    
    # Explicit language boost ("decided", "confirmed", "agreed")
    explicit_boost = 0.10 if contains_explicit_marker(candidate.source_text) else 0
    
    return min(1.0, base + corroboration_boost + context_boost + explicit_boost)
```

---

## 7. WORKSPACE ASSIGNMENT

After extraction, each candidate must be assigned to a workspace:

```python
def assign_to_workspace(
    candidate: ExtractionCandidate,
    active_workspaces: List[Workspace],
    current_workspace_id: Optional[str]
) -> str:
    
    # If user has already selected a workspace, use it
    if current_workspace_id:
        return current_workspace_id
    
    # Score each workspace by relevance
    scores = {}
    for workspace in active_workspaces:
        score = compute_workspace_relevance(candidate, workspace)
        scores[workspace.id] = score
    
    if not scores:
        return SUGGEST_NEW_WORKSPACE
    
    best_workspace_id = max(scores, key=scores.get)
    best_score = scores[best_workspace_id]
    
    if best_score < WORKSPACE_MATCH_THRESHOLD:  # 0.6
        return SUGGEST_NEW_WORKSPACE
    
    return best_workspace_id

def compute_workspace_relevance(
    candidate: ExtractionCandidate,
    workspace: Workspace
) -> float:
    # Semantic similarity between candidate and workspace summary
    semantic_score = cosine_similarity(
        candidate.embedding_vector,
        workspace.summary_embedding
    )
    
    # Entity overlap
    workspace_entities = workspace.get_top_entities()
    candidate_entities = extract_entity_names(candidate)
    overlap = len(set(candidate_entities) & set(workspace_entities))
    entity_score = min(1.0, overlap / max(len(candidate_entities), 1) * 1.5)
    
    # Recency (recently active workspace gets boost)
    days_since_active = (datetime.utcnow() - workspace.last_active).days
    recency_score = max(0, 1 - days_since_active / 30)
    
    return (semantic_score * 0.5) + (entity_score * 0.3) + (recency_score * 0.2)
```

---

## 8. EXTRACTION QUALITY BENCHMARKS

### Test Suite Structure

The project ships with 500 labeled conversation pairs:
- 100 developer conversations
- 100 research conversations
- 100 product management conversations
- 100 creative project conversations
- 100 edge cases (ambiguous, contradictory, sparse)

### Target Metrics

| Metric | Target | Minimum Acceptable |
|--------|--------|-------------------|
| Precision (all types) | > 85% | > 75% |
| Recall (all types) | > 75% | > 65% |
| Goal detection precision | > 88% | > 78% |
| Decision detection precision | > 82% | > 72% |
| False positive rate | < 10% | < 15% |
| Processing time (per turn) | < 500ms | < 1500ms |

### Known Hard Cases (Expect Lower Performance)

- Hypothetical discussions ("what if we used X")
- Negated plans ("we could use X, but won't")
- Sarcastic or ironic statements
- Very short messages (< 2 sentences)
- Heavy jargon without workspace context

**Rule for hard cases:** When in doubt, **don't extract**. False negatives are less harmful than false positives.

---

## 9. SENSITIVE DATA FILTER (PRE-EXTRACTION)

This runs BEFORE any extraction. If triggered, the entire message pair is skipped.

```python
SENSITIVE_PATTERNS = [
    # API Keys
    r'sk-[A-Za-z0-9]{32,}',           # OpenAI
    r'AKIA[A-Z0-9]{16}',               # AWS
    r'AIza[0-9A-Za-z-_]{35}',          # Google
    r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', # Bearer tokens
    
    # Credentials
    r'password["\s:=]+[^\s,}{]+',
    r'secret["\s:=]+[^\s,}{]+',
    r'private_key["\s:=]+[^\s,}{]+',
    
    # PII
    r'\b\d{3}-\d{2}-\d{4}\b',          # SSN
    r'\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b',  # Credit card
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email (optional)
]

def contains_sensitive_data(text: str) -> bool:
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
```

---

## 10. EXTRACTION PIPELINE MAIN LOOP

```python
async def process_capture(capture: CaptureEvent) -> ProcessingResult:
    # 1. Sensitive data check
    if contains_sensitive_data(capture.user_message + capture.ai_response):
        logger.info(f"Skipped capture {capture.id}: sensitive data detected")
        return ProcessingResult(skipped=True, reason="sensitive_data")
    
    # 2. Trivial content check (very short, no information content)
    if is_trivial(capture.user_message, capture.ai_response):
        return ProcessingResult(skipped=True, reason="trivial_content")
    
    # 3. Run extraction passes
    full_text = f"USER: {capture.user_message}\nAI: {capture.ai_response}"
    
    rule_candidates = extract_rule_based(full_text)
    ner_candidates = extract_ner_based(full_text)
    
    # Only run LLM if needed
    llm_candidates = []
    if should_run_llm_pass(full_text, rule_candidates, ner_candidates):
        llm_candidates = await extract_llm_based(full_text, capture.workspace_id)
    
    # 4. Merge and score
    all_candidates = merge_extraction_passes(rule_candidates, ner_candidates, llm_candidates)
    scored_candidates = [score_candidate(c) for c in all_candidates]
    
    # 5. Filter by minimum threshold
    valid_candidates = [c for c in scored_candidates if c.confidence >= MIN_CONFIDENCE]  # 0.60
    
    # 6. Assign to workspace
    workspace_id = assign_to_workspace(valid_candidates, capture.workspace_id)
    
    # 7. Commit or queue
    auto_committed = []
    pending_review = []
    
    for candidate in valid_candidates:
        if candidate.confidence >= AUTO_COMMIT_THRESHOLD:  # 0.80
            node = commit_to_graph(candidate, workspace_id)
            auto_committed.append(node)
        else:
            pending = queue_for_review(candidate, workspace_id)
            pending_review.append(pending)
    
    return ProcessingResult(
        auto_committed=auto_committed,
        pending_review=pending_review,
        skipped=False
    )
```
