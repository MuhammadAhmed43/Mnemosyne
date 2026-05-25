# Plan 02 — Extraction Pipeline

> Covers: Doc 06 (Cognitive Extraction), Doc 14 (Do's and Don'ts)

---

## Architecture Overview

```
Capture arrives
  ↓
[Sensitive Data Filter] ── BLOCKED → discard, log pattern only
  ↓ CLEAN
[Pass 1: Rule-Based] → tech stack, decisions, goals, deadlines
  ↓ candidates[]
[Pass 2: NER/Linguistic] → entities, relationships, context
  ↓ candidates[]
[Pass 3: LLM (optional)] → complex goals, preferences, implicit decisions
  ↓ candidates[]
[Hypothetical Detector] → filter out "what if" statements
  ↓
[Confidence Scorer] → merge multi-pass, compute final scores
  ↓
[Router]
  ├── confidence >= 0.80 → AUTO_COMMIT to graph
  ├── 0.60 <= confidence < 0.80 → PENDING_REVIEW
  └── confidence < 0.60 → DISCARD
```

---

## File 1: backend/extraction/sensitive_filter.py

```python
import re
from backend.models.extraction import SensitivityCheckResult

SENSITIVE_PATTERNS = [
    # API Keys
    (r'sk-[A-Za-z0-9]{20,}', "OpenAI API key"),
    (r'sk-ant-[A-Za-z0-9\-]{20,}', "Anthropic API key"),
    (r'AKIA[A-Z0-9]{16}', "AWS Access Key"),
    (r'AIza[0-9A-Za-z\-_]{35}', "Google API key"),
    (r'github_pat_[A-Za-z0-9_]{82}', "GitHub PAT"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub token"),
    (r'xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}', "Slack bot token"),

    # Generic credentials
    (r'(?:api[_\-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*["\']?[A-Za-z0-9\-_+/]{20,}',
     "Generic credential"),
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', "Bearer token"),

    # Private keys / certs
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private key"),
    (r'-----BEGIN CERTIFICATE-----', "Certificate"),

    # PII
    (r'\b\d{3}-\d{2}-\d{4}\b', "SSN"),
    (r'\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b', "Credit card"),
    (r'\b3[47]\d{13}\b', "Amex card"),

    # Connection strings
    (r'(?:postgres|mysql|mongodb|redis):\/\/[^:\s]+:[^@\s]+@', "Database connection string"),
    (r'(?:POSTGRES|MYSQL|DATABASE)_(?:URL|URI|PASSWORD)\s*=\s*\S+', "DB env var"),
]

# Pre-compile for performance (<10ms target)
_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in SENSITIVE_PATTERNS]

def contains_sensitive_data(text: str) -> SensitivityCheckResult:
    """First gate in pipeline. Must run <10ms."""
    for pattern, label in _COMPILED:
        if pattern.search(text):
            return SensitivityCheckResult(is_sensitive=True, pattern_matched=label)
    return SensitivityCheckResult(is_sensitive=False)

def check_custom_blocked_terms(text: str, terms: list[str]) -> SensitivityCheckResult:
    """User-defined blocked terms (from settings)."""
    text_lower = text.lower()
    for term in terms:
        if term.lower() in text_lower:
            return SensitivityCheckResult(is_sensitive=True,
                                          pattern_matched=f"Custom: {term}")
    return SensitivityCheckResult(is_sensitive=False)
```

---

## File 2: backend/extraction/rule_based.py

```python
import re
from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

# --- TECHNOLOGY PATTERNS ---
TECH_ENTITIES = [
    "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt",
    "FastAPI", "Django", "Flask", "Express", "Spring",
    "PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis", "Cassandra",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure",
    "Python", "TypeScript", "JavaScript", "Rust", "Go", "Java",
    "TensorFlow", "PyTorch", "scikit-learn", "spaCy",
    # ... 200+ entries from Doc 06
]

TECH_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(t) for t in TECH_ENTITIES) + r')\b',
    re.IGNORECASE
)

# Contextual patterns: "we use X", "built with X", "running on X"
TECH_CONTEXT = re.compile(
    r'(?:(?:we|I|our team)\s+)?'
    r'(?:use|using|built with|running on|switched to|migrated to|chose|adopted|deployed on)\s+'
    r'([A-Z][A-Za-z0-9\.\-\+]+(?:\s+\d+[\.\d]*)?)',
    re.IGNORECASE
)

# --- DECISION PATTERNS ---
DECISION_TRIGGERS = re.compile(
    r'(?:we\s+)?(?:decided|agreed|went with|chose|committed to|'
    r'settled on|concluded|determined|resolved to|'
    r'will\s+(?:go with|use|implement|build|switch))',
    re.IGNORECASE
)

# --- GOAL PATTERNS ---
GOAL_TRIGGERS = re.compile(
    r'(?:(?:my|our|the)\s+)?'
    r'(?:goal|objective|target|aim|plan|deadline|milestone|priority)\s+'
    r'(?:is|was|should be|will be)',
    re.IGNORECASE
)

ACTION_GOALS = re.compile(
    r'(?:need to|have to|must|should|want to|going to|plan to|'
    r'trying to|working on|aiming to|hoping to)\s+(.+?)(?:\.|$)',
    re.IGNORECASE
)

# --- PROBLEM / BLOCKER PATTERNS ---
PROBLEM_TRIGGERS = re.compile(
    r'(?:the problem|the issue|struggling with|stuck on|blocked by|'
    r'can\'t figure out|doesn\'t work|bug in|error with|failing)',
    re.IGNORECASE
)

# --- PREFERENCE PATTERNS ---
PREFERENCE_TRIGGERS = re.compile(
    r'(?:I prefer|I like|I always|I never|I tend to|'
    r'my style|I want you to|please always|please don\'t|'
    r'don\'t (?:use|suggest|recommend))',
    re.IGNORECASE
)

# --- EVENT / MILESTONE PATTERNS (Doc 04 §4 — Episodic) ---
EVENT_TRIGGERS = re.compile(
    r'(?:we shipped|we launched|we deployed|we released|we completed|'
    r'we finished|we presented|we submitted|we merged|we published|'
    r'just shipped|just launched|just deployed|just released|'
    r'successfully (?:deployed|launched|shipped|completed)|'
    r'went live|pushed to production|demo(?:\'d|ed)|'
    r'milestone|breakthrough|achieved|accomplishment)',
    re.IGNORECASE
)

# --- RATIONALE PATTERNS (Doc 06 §3.2) ---
# Used to extract the WHY behind decisions into structured_data.rationale
RATIONALE_TRIGGERS = re.compile(
    r'(?:because|reason(?:\s*:|\s+is|\s+was)|since|due to|'
    r'to (?:avoid|prevent|reduce|improve))\s+(.+?)(?:\.|$)',
    re.IGNORECASE
)

# --- COMPLETION PATTERNS (Doc 06 §3.3) ---
# Detects completed goals/tasks to trigger GOAL → COMPLETED state change
COMPLETION_TRIGGERS = re.compile(
    r'(?:completed|finished|shipped|launched|deployed|done with|wrapped up)\s+(.+?)(?:\.|$)|'
    r'(.+?)\s+(?:is done|is complete|is finished|is shipped|is live)',
    re.IGNORECASE
)

class RuleBasedExtractor:
    """Pass 1: Fast regex-based extraction. Always available."""

    def extract(self, user_msg: str, ai_msg: str) -> list[ExtractionCandidate]:
        combined = f"{user_msg}\n{ai_msg}"
        candidates = []

        # Tech stack — Doc 06 §3.1: confidence=0.90 for rule-based tech extraction
        for match in TECH_CONTEXT.finditer(combined):
            candidates.append(ExtractionCandidate(
                node_type=NodeType.TECHNICAL_FACT,
                content=match.group(0).strip(),
                structured_data={"entity": "tech", "value": match.group(1)},
                confidence=0.90,  # Doc 06 §3.1: rule-based tech facts = 0.90 (auto-commit eligible)
                source_pass="rule_based",
                evidence=f"Pattern: tech_context at pos {match.start()}"
            ))

        # Decisions
        for match in DECISION_TRIGGERS.finditer(combined):
            sentence = self._extract_sentence(combined, match.start())
            candidates.append(ExtractionCandidate(
                node_type=NodeType.DECISION,
                content=sentence,
                confidence=0.78,
                source_pass="rule_based",
                evidence=f"Pattern: decision_trigger"
            ))

        # Goals
        for match in GOAL_TRIGGERS.finditer(combined):
            sentence = self._extract_sentence(combined, match.start())
            candidates.append(ExtractionCandidate(
                node_type=NodeType.GOAL,
                content=sentence,
                confidence=0.72,
                source_pass="rule_based",
                evidence="Pattern: goal_trigger"
            ))

        # Problems
        for match in PROBLEM_TRIGGERS.finditer(combined):
            sentence = self._extract_sentence(combined, match.start())
            candidates.append(ExtractionCandidate(
                node_type=NodeType.PROBLEM,
                content=sentence,
                confidence=0.70,
                source_pass="rule_based",
                evidence="Pattern: problem_trigger"
            ))

        # Preferences
        for match in PREFERENCE_TRIGGERS.finditer(combined):
            sentence = self._extract_sentence(combined, match.start())
            candidates.append(ExtractionCandidate(
                node_type=NodeType.PREFERENCE,
                content=sentence,
                confidence=0.68,
                source_pass="rule_based",
                evidence="Pattern: preference_trigger"
            ))

        # Events / Milestones (Doc 04 §4 — Episodic Memory)
        for match in EVENT_TRIGGERS.finditer(combined):
            sentence = self._extract_sentence(combined, match.start())
            candidates.append(ExtractionCandidate(
                node_type=NodeType.EVENT,
                content=sentence,
                structured_data={"outcome": "positive", "entities_involved": []},
                confidence=0.74,
                source_pass="rule_based",
                evidence="Pattern: event_trigger"
            ))

        # Completions (Doc 06 §3.3) — signal for GOAL → COMPLETED state update
        for match in COMPLETION_TRIGGERS.finditer(combined):
            subject = (match.group(1) or match.group(2) or "").strip()
            if subject:
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.EVENT,
                    content=self._extract_sentence(combined, match.start()),
                    structured_data={
                        "outcome": "positive",
                        "completed_subject": subject,
                        "triggers_goal_completion": True  # Flag for graph_service to check
                    },
                    confidence=0.76,
                    source_pass="rule_based",
                    evidence="Pattern: completion_trigger"
                ))

        # Rationale extraction (Doc 06 §3.2) — enrich DECISION nodes with WHY
        # Applied as post-processing: attach rationale to the most recent decision candidate
        rationales = []
        for match in RATIONALE_TRIGGERS.finditer(combined):
            rationales.append(match.group(1).strip())
        if rationales:
            # Attach to last decision candidate found
            for c in reversed(candidates):
                if c.node_type == NodeType.DECISION:
                    c.structured_data["rationale"] = rationales[0]
                    break

        return candidates

    def _extract_sentence(self, text: str, pos: int) -> str:
        """Extract the full sentence containing position `pos`."""
        start = text.rfind('.', 0, pos)
        start = 0 if start == -1 else start + 1
        end = text.find('.', pos)
        end = len(text) if end == -1 else end + 1
        return text[start:end].strip()
```

---

## File 3: backend/extraction/hypothetical_detector.py

```python
import re

HYPOTHETICAL_MARKERS = re.compile(
    r'\b(?:what if|imagine if|suppose we|could we|we might|'
    r'one option is|alternatively|we could consider|theoretically|'
    r'just brainstorming|hypothetically|maybe we should|'
    r'have you considered|another approach|what about)\b',
    re.IGNORECASE
)

NEGATION_MARKERS = re.compile(
    r'\b(?:we won\'t|we don\'t|not using|rejected|ruled out|'
    r'decided against|dropped|removed|abandoned|scrapped|'
    r'that was wrong|incorrect|no longer)\b',
    re.IGNORECASE
)

def is_hypothetical(text: str) -> bool:
    return bool(HYPOTHETICAL_MARKERS.search(text))

def is_negated(text: str, entity: str) -> bool:
    """Check if entity appears in a negated context."""
    entity_pos = text.lower().find(entity.lower())
    if entity_pos == -1:
        return False
    window = text[max(0, entity_pos - 80):entity_pos + len(entity) + 40]
    return bool(NEGATION_MARKERS.search(window))

def filter_hypotheticals(
    candidates: list["ExtractionCandidate"]
) -> list["ExtractionCandidate"]:
    """Remove candidates from hypothetical/negated contexts."""
    filtered = []
    for c in candidates:
        if is_hypothetical(c.evidence) or is_hypothetical(c.content):
            c.confidence *= 0.3  # Heavily penalize, don't discard
        if c.node_type == NodeType.TECHNICAL_FACT:
            if is_negated(c.content, c.structured_data.get("value", "")):
                continue  # Drop negated tech facts entirely
        filtered.append(c)
    return filtered
```

---

## File 4: backend/extraction/ner_extractor.py

```python
import spacy

class NERExtractor:
    """Pass 2: spaCy NER + dependency parsing."""

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
        # Add custom tech entity ruler
        ruler = self.nlp.add_pipe("entity_ruler", before="ner")
        patterns = [
            {"label": "TECH", "pattern": t}
            for t in TECH_ENTITIES  # from rule_based.py
        ]
        ruler.add_patterns(patterns)

    def extract(self, user_msg: str, ai_msg: str) -> list[ExtractionCandidate]:
        candidates = []
        doc = self.nlp(f"{user_msg}\n{ai_msg}")

        # Named entities
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.ENTITY,
                    content=ent.text,
                    structured_data={"entity_type": "person", "role": None},
                    confidence=0.72,
                    source_pass="ner",
                    evidence=f"spaCy NER: {ent.label_}"
                ))
            elif ent.label_ == "ORG":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.ENTITY,
                    content=ent.text,
                    structured_data={"entity_type": "org"},
                    confidence=0.70,
                    source_pass="ner",
                    evidence=f"spaCy NER: {ent.label_}"
                ))
            elif ent.label_ in ("DATE", "TIME"):
                # Check if it's a deadline context
                sent = ent.sent.text
                if any(w in sent.lower() for w in ["deadline", "due", "by", "before", "launch"]):
                    candidates.append(ExtractionCandidate(
                        node_type=NodeType.TASK,
                        content=sent.strip(),
                        structured_data={"due_date": ent.text},
                        confidence=0.65,
                        source_pass="ner",
                        evidence=f"spaCy NER: deadline context"
                    ))
            elif ent.label_ == "TECH":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.TECHNICAL_FACT,
                    content=f"Uses {ent.text}",
                    structured_data={"entity": "tech", "value": ent.text},
                    confidence=0.68,
                    source_pass="ner",
                    evidence=f"Custom entity ruler: TECH"
                ))
            # Doc 06 §4.2: PRODUCT entity type
            elif ent.label_ == "PRODUCT":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.ENTITY,
                    content=ent.text,
                    structured_data={"entity_type": "product"},
                    confidence=0.65,
                    source_pass="ner",
                    evidence=f"spaCy NER: PRODUCT"
                ))
            # Doc 06 §4.2: CONCEPT entity type (via custom ruler)
            elif ent.label_ == "CONCEPT":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.ENTITY,
                    content=ent.text,
                    structured_data={"entity_type": "concept"},
                    confidence=0.60,
                    source_pass="ner",
                    evidence=f"Custom entity ruler: CONCEPT"
                ))
            # Doc 06 §4.2: MONEY = budget or financial reference
            elif ent.label_ == "MONEY":
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.TECHNICAL_FACT,
                    content=f"Budget/cost reference: {ent.text}",
                    structured_data={"entity": "budget", "value": ent.text,
                                     "category": "financial"},
                    confidence=0.62,
                    source_pass="ner",
                    evidence=f"spaCy NER: MONEY"
                ))

        # Relationship extraction via dependency parsing
        candidates.extend(self._extract_relationships(doc))

        return candidates

    def _extract_relationships(self, doc) -> list[ExtractionCandidate]:
        """Extract subject-verb-object triples for edge creation."""
        relationships = []
        for token in doc:
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                subjects = [c for c in token.children if c.dep_ in ("nsubj", "nsubjpass")]
                objects = [c for c in token.children if c.dep_ in ("dobj", "pobj", "attr")]
                for subj in subjects:
                    for obj in objects:
                        relationships.append(ExtractionCandidate(
                            node_type=NodeType.ENTITY,
                            content=f"{subj.text} {token.text} {obj.text}",
                            structured_data={
                                "subject": subj.text,
                                "verb": token.text,
                                "object": obj.text
                            },
                            confidence=0.55,
                            source_pass="ner",
                            evidence="Dependency parse: SVO triple"
                        ))
        return relationships
```

---

## File 5: backend/extraction/llm_extractor.py

```python
import httpx
import json

# Doc 06 §5.3 — system prompt (sets role and format constraints)
LLM_SYSTEM_PROMPT = """You are a cognitive extraction engine. Your job is to extract structured
memory from AI conversation snippets.

Extract ONLY what is explicitly stated or very strongly implied.
Do NOT infer things that aren't there.
Do NOT extract generic or obvious facts.

Return ONLY valid JSON. No preamble, no explanation."""

# Doc 06 §5.3 — grouped format with type-specific structured_data
LLM_USER_PROMPT = """Extract structured memory from this conversation turn:

USER: {user_message}

AI: {ai_response}

Workspace context (for disambiguation): {workspace_summary}

Output format:
{{
  "goals": [
    {{"content": "exact goal statement", "priority": "HIGH|MEDIUM|LOW",
      "deadline": "ISO date or null", "status": "ACTIVE|COMPLETED|ABANDONED"}}
  ],
  "decisions": [
    {{"content": "what was decided", "rationale": "why (if stated)",
      "reversible": true}}
  ],
  "preferences": [
    {{"content": "behavioral preference", "domain": "communication|technical|workflow|other"}}
  ],
  "open_problems": [
    {{"content": "unresolved issue", "severity": "BLOCKING|IMPORTANT|MINOR"}}
  ],
  "technical_facts": [
    {{"entity": "what", "attribute": "property", "value": "current value"}}
  ]
}}

Return empty arrays for types not found. Do NOT add extra keys."""

class LLMExtractor:
    """Pass 3: Local LLM (Phi-4 Mini via Ollama) with optional cloud fallback."""

    def __init__(self, ollama_url: str = "http://localhost:11434",
                 model: str = "phi4-mini", network_logger=None, cloud_endpoint: str = ""):
        self.ollama_url = ollama_url
        self.model = model
        self._network_logger = network_logger
        self._cloud_endpoint = cloud_endpoint
        self._available: bool | None = None

    async def _call_cloud_llm(self, prompt: str) -> str:
        """Cloud LLM fallback — only when user has enabled it and Ollama is unavailable."""
        # Log the outbound call for UC-22 privacy audit (Doc 13 §6)
        if self._network_logger:
            await self._network_logger.log(
                destination=self._cloud_endpoint,
                purpose="cloud_llm_fallback",
                is_internal=False,
                bytes_sent=len(prompt.encode())
            )
        # Cloud LLM HTTP call placeholder
        return ""

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                models = [m["name"] for m in resp.json().get("models", [])]
                self._available = any(self.model in m for m in models)
        except Exception:
            self._available = False
        return self._available

    async def extract(
        self, user_msg: str, ai_msg: str,
        workspace_summary: str = "No workspace context available."
    ) -> list[ExtractionCandidate]:
        if not await self.is_available():
            return []  # Graceful degradation

        # Doc 06 §5.3: separate system and user prompts, inject workspace_summary
        user_prompt = LLM_USER_PROMPT.format(
            user_message=user_msg[:3000],
            ai_response=ai_msg[:3000],
            workspace_summary=workspace_summary[:500]
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "system": LLM_SYSTEM_PROMPT,
                        "prompt": user_prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 1024}
                    }
                )
                raw = resp.json()["response"]
                return self._parse_response(raw)
        except Exception as e:
            logger.warning(f"LLM extraction failed: {type(e).__name__}")
            return []

    def _parse_response(self, raw: str) -> list[ExtractionCandidate]:
        """Parse Doc 06 §5.3 grouped JSON output into ExtractionCandidates."""
        try:
            cleaned = re.sub(r'```(?:json)?|```', '', raw).strip()
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return []
        except json.JSONDecodeError:
            return []

        candidates = []

        # goals
        for g in data.get("goals", []):
            if len(g.get("content", "")) > 10:
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.GOAL,
                    content=g["content"][:500],
                    structured_data={
                        "priority": g.get("priority", "MEDIUM"),
                        "deadline": g.get("deadline"),
                        "status": g.get("status", "ACTIVE")
                    },
                    confidence=0.75,
                    source_pass="llm",
                    evidence=f"LLM goal extraction"
                ))

        # decisions
        for d in data.get("decisions", []):
            if len(d.get("content", "")) > 10:
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.DECISION,
                    content=d["content"][:500],
                    structured_data={
                        "rationale": d.get("rationale", ""),
                        "reversible": d.get("reversible", True)
                    },
                    confidence=0.75,
                    source_pass="llm",
                    evidence="LLM decision extraction"
                ))

        # preferences
        for p in data.get("preferences", []):
            if len(p.get("content", "")) > 5:
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.PREFERENCE,
                    content=p["content"][:500],
                    structured_data={"domain": p.get("domain", "other")},
                    confidence=0.70,
                    source_pass="llm",
                    evidence="LLM preference extraction"
                ))

        # open_problems
        for op in data.get("open_problems", []):
            if len(op.get("content", "")) > 5:
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.PROBLEM,
                    content=op["content"][:500],
                    structured_data={"severity": op.get("severity", "IMPORTANT")},
                    confidence=0.72,
                    source_pass="llm",
                    evidence="LLM problem extraction"
                ))

        # technical_facts
        for tf in data.get("technical_facts", []):
            if tf.get("entity") and tf.get("value"):
                candidates.append(ExtractionCandidate(
                    node_type=NodeType.TECHNICAL_FACT,
                    content=f"{tf['entity']} {tf.get('attribute','is')} {tf['value']}",
                    structured_data={
                        "entity": tf["entity"],
                        "attribute": tf.get("attribute", "technology"),
                        "value": tf["value"]
                    },
                    confidence=0.75,
                    source_pass="llm",
                    evidence="LLM tech fact extraction"
                ))

        return candidates
```

---

## File 6: backend/extraction/confidence_scorer.py

```python
from collections import defaultdict

# From Doc 14 — Engineering Laws
AUTO_COMMIT_THRESHOLD = 0.80
MIN_CONFIDENCE = 0.60

# Pass weights for multi-pass agreement
PASS_WEIGHTS = {
    "rule_based": 0.30,
    "ner": 0.25,
    "llm": 0.45,
}

# Boost per additional corroborating pass (Doc 06 §6)
CORROBORATION_BOOST = 0.08       # per corroborating pass
CONTEXT_BOOST = 0.05             # if workspace context corroborates
EXPLICIT_LANGUAGE_BOOST = 0.10  # for words like "decided", "confirmed"

EXPLICIT_MARKERS = [
    "decided", "confirmed", "agreed", "committed", "finalized",
    "resolved", "settled", "concluded", "must", "always", "never"
]

class ConfidenceScorer:

    def merge_candidates(
        self, candidates: list[ExtractionCandidate]
    ) -> list[ExtractionCandidate]:
        """Merge candidates from multiple passes; track corroborated_by per Doc 06 §6."""
        groups = self._group_similar(candidates)
        merged = []

        for key, group in groups.items():
            best = max(group, key=lambda c: c.confidence)
            passes = set(c.source_pass for c in group)

            # Track corroborating passes (Doc 06 §6)
            best.corroborated_by = [c.source_pass for c in group if c is not best]

            if len(group) == 1:
                # Single-pass: normalise weight
                weight = PASS_WEIGHTS.get(best.source_pass, 0.3)
                best.confidence = min(best.confidence * (weight / 0.45), best.confidence)
            else:
                # Weighted average base
                weighted_sum = sum(
                    c.confidence * PASS_WEIGHTS.get(c.source_pass, 0.3)
                    for c in group
                )
                total_weight = sum(
                    PASS_WEIGHTS.get(c.source_pass, 0.3) for c in group
                )
                best.confidence = weighted_sum / total_weight

            # Apply Doc 06 §6 boosts
            best.confidence = self._compute_final_confidence(best)
            best.confidence = min(best.confidence, 0.98)
            best.source_pass = "+".join(sorted(passes))
            merged.append(best)

        return [c for c in merged if c.confidence >= MIN_CONFIDENCE]

    def _compute_final_confidence(self, candidate: ExtractionCandidate) -> float:
        """Apply three boosts from Doc 06 §6."""
        score = candidate.confidence

        # Corroboration boost (+0.08 per additional pass)
        corroboration_boost = len(getattr(candidate, 'corroborated_by', [])) * CORROBORATION_BOOST

        # Explicit language boost (+0.10 for strong markers)
        explicit_boost = EXPLICIT_LANGUAGE_BOOST if any(
            m in candidate.content.lower() for m in EXPLICIT_MARKERS
        ) else 0.0

        # Context boost (+0.05) — applied later by ExtractionPipeline with workspace data
        # Stored as a flag for the pipeline layer
        candidate._needs_context_check = True

        return min(1.0, score + corroboration_boost + explicit_boost)

    def _group_similar(self, candidates):
        """Group candidates by semantic similarity (simple: same type + overlap)."""
        groups = defaultdict(list)
        for c in candidates:
            # Simple key: type + first 5 significant words
            words = [w.lower() for w in c.content.split()
                     if len(w) > 3][:5]
            key = (c.node_type, tuple(sorted(words)))
            groups[key].append(c)
        return groups

    def route_candidates(self, candidates: list[ExtractionCandidate]) -> dict:
        """Route merged candidates to auto_commit, pending_review, or discard."""
        result = {"auto_commit": [], "pending_review": [], "discarded": []}
        for c in candidates:
            if c.confidence >= AUTO_COMMIT_THRESHOLD:
                result["auto_commit"].append(c)
            elif c.confidence >= MIN_CONFIDENCE:
                result["pending_review"].append(c)
            else:
                result["discarded"].append(c)
        return result
```

---

## File 7a: backend/extraction/importance_scorer.py

> **Gap fix — Doc 04 §9: Initial Importance Scoring**

```python
from backend.models.enums import NodeType

# Base scores by node type (from Doc 04 §9)
TYPE_WEIGHTS = {
    NodeType.DECISION: 0.80,
    NodeType.GOAL: 0.75,
    NodeType.PROBLEM: 0.70,
    NodeType.PREFERENCE: 0.70,
    NodeType.TECHNICAL_FACT: 0.65,
    NodeType.EVENT: 0.60,            # Doc 04 §9
    NodeType.ENTITY: 0.55,
    NodeType.TASK: 0.50,
    NodeType.INSIGHT: 0.60,
    NodeType.CONSTRAINT: 0.65,
    NodeType.RELATIONSHIP: 0.55,     # Doc 04 §2.2
    NodeType.WORKSPACE_SUMMARY: 0.40,
    NodeType.USER_NOTE: 0.90,        # Manual entry = high importance
}

HIGH_IMPORTANCE_KEYWORDS = [
    "never", "always", "critical", "must", "blocked",
    "decided", "final", "confirmed", "deadline", "launch",
    "breaking", "urgent", "production", "security",
]

def compute_initial_importance(node_type: NodeType, content: str,
                                extraction_confidence: float,
                                source_platform: str) -> float:
    """
    Computes initial importance score for a new node.
    From Doc 04 §9 — type weights × confidence modifier × keyword boost.
    """
    # Base score from node type
    score = TYPE_WEIGHTS.get(node_type, 0.5)

    # Extraction confidence modifier: scale between 0.7 and 1.0
    score *= (0.7 + 0.3 * extraction_confidence)

    # Keyword boosters
    keyword_hits = sum(1 for k in HIGH_IMPORTANCE_KEYWORDS if k in content.lower())
    score = min(1.0, score + 0.05 * keyword_hits)

    # User-entered nodes get max score
    if source_platform == "manual":
        score = max(score, 0.9)

    return round(min(score, 1.0), 3)
```

Called in `ExtractionPipeline.run()` after routing — each committed node gets its `importance_score` set via this function.

---

## File 8: backend/extraction/pipeline.py

```python
from backend.extraction.sensitive_filter import contains_sensitive_data, check_custom_blocked_terms
from backend.extraction.rule_based import RuleBasedExtractor
from backend.extraction.ner_extractor import NERExtractor
from backend.extraction.llm_extractor import LLMExtractor
from backend.extraction.hypothetical_detector import filter_hypotheticals
from backend.extraction.confidence_scorer import ConfidenceScorer

class ExtractionPipeline:
    """
    Main orchestrator for the 3-pass cognitive extraction engine.
    Uses LangGraph for state machine management.
    """

    def __init__(self, config: MnemosyneConfig):
        self.rule_based = RuleBasedExtractor()
        self.ner = NERExtractor()
        self.llm = LLMExtractor(config.ollama_url, config.ollama_model)
        self.scorer = ConfidenceScorer()
        self.config = config

    async def run(self, capture: CaptureRecord) -> ExtractionResult:
        start = time.monotonic()
        user_msg = capture.user_message
        ai_msg = capture.ai_response

        # Gate 1: Sensitive data filter (MUST be first, <10ms)
        sensitivity = contains_sensitive_data(f"{user_msg}\n{ai_msg}")
        if sensitivity.is_sensitive:
            logger.info(f"Capture {capture.id} blocked: {sensitivity.pattern_matched}")
            return ExtractionResult(
                capture_id=capture.id, duration_ms=0,
            )

        # Custom blocked terms
        settings = await self._get_settings()
        custom_check = check_custom_blocked_terms(
            f"{user_msg}\n{ai_msg}", settings.custom_blocked_terms
        )
        if custom_check.is_sensitive:
            return ExtractionResult(capture_id=capture.id, duration_ms=0)

        # Trivial message filter — aligned with Doc 10 §2: len(combined) < 50 chars
        combined_text = f"{user_msg}\n{ai_msg}"
        if len(combined_text) < 50:
            return ExtractionResult(
                capture_id=capture.id,
                duration_ms=int((time.monotonic() - start) * 1000)
            )

        # Pass 1: Rule-based (always runs, <50ms)
        rule_candidates = self.rule_based.extract(user_msg, ai_msg)

        # Pass 2: NER (always runs, <30ms)
        ner_candidates = self.ner.extract(user_msg, ai_msg)

        # Pass 3: LLM — Doc 06 §5.1: ONLY triggered when conditions met
        llm_candidates = []
        combined_text = f"{user_msg}\n{ai_msg}"
        if self._should_run_llm_pass(combined_text, rule_candidates, ner_candidates):
            ws_summary = await self._get_workspace_summary(capture.workspace_id)
            llm_candidates = await self.llm.extract(user_msg, ai_msg, ws_summary)

        # Combine all candidates
        all_candidates = rule_candidates + ner_candidates + llm_candidates

        # Filter hypotheticals and negations
        all_candidates = filter_hypotheticals(all_candidates)

        # Merge multi-pass and compute final confidence
        merged = self.scorer.merge_candidates(all_candidates)

        # Route by confidence threshold
        routed = self.scorer.route_candidates(merged)

        duration_ms = int((time.monotonic() - start) * 1000)

        return ExtractionResult(
            capture_id=capture.id,
            auto_committed=[],     # Will be committed by extraction_service
            pending_review=routed["pending_review"],
            discarded=routed["discarded"],
            duration_ms=duration_ms,
            # _auto_commit_candidates stored temporarily for service layer
            _routed=routed
        )

    def _should_run_llm_pass(
        self,
        text: str,
        rule_candidates: list,
        ner_candidates: list
    ) -> bool:
        """Doc 06 §5.1: Gate LLM pass — only run when truly needed.

        Four conditions (all four must be checked — Doc 06 §5.1):
          1. Rule/NER already found goals or decisions → skip LLM
          2. Text is too short (< 3 sentences) → skip LLM
          3. No first-person planning language → skip LLM
          4. Multi-topic complexity: text covers >= 3 distinct cognitive
             categories simultaneously → RUN LLM (even if short/no first-person)
        """
        combined_candidates = rule_candidates + ner_candidates

        # Condition 1: rule/NER already caught key types — no need for LLM
        has_goals_or_decisions = any(
            c.node_type in (NodeType.GOAL, NodeType.DECISION)
            for c in combined_candidates
        )
        if has_goals_or_decisions:
            return False

        # Condition 4 (checked before 2 & 3 intentionally):
        # Multi-topic complexity — text simultaneously discusses multiple cognitive
        # categories. Short messages that pack in goals + tech + decisions in one turn
        # benefit most from LLM extraction. (Doc 06 §5.1 condition 4)
        candidate_types = {c.node_type for c in combined_candidates}
        MULTI_TOPIC_THRESHOLD = 3  # >= 3 distinct node types in one turn
        if len(candidate_types) >= MULTI_TOPIC_THRESHOLD:
            return True

        # Condition 2: too short for LLM to add value
        sentence_count = text.count('.') + text.count('!') + text.count('?')
        if sentence_count < 3:
            return False

        # Condition 3: no first-person planning/preference signal
        first_person = re.search(
            r'\b(?:I |we |my |our )(?:plan|want|need|going to|prefer|think|feel|decided)',
            text, re.IGNORECASE
        )
        if not first_person:
            return False

        return True

    async def _get_workspace_summary(self, workspace_id: str) -> str:
        """Fetch workspace summary text for LLM disambiguation context."""
        try:
            ws = await self.workspace_repo.get(workspace_id)
            return ws.summary_text or ws.description or ""
        except Exception:
            return ""
```

---

## Key Design Decisions

| Decision | Rationale (from Docs 06, 14) |
|----------|------------------------------|
| Sensitive filter runs FIRST | Doc 14 §1: "before anything else" |
| Rule-based always runs | Zero dependencies, <50ms |
| NER always runs | spaCy en_core_web_sm = 12MB, <30ms |
| LLM is optional | Graceful degradation if Ollama down |
| Hypotheticals filtered | Doc 14 §3: "don't extract from what-ifs" |
| Multi-pass agreement boosts confidence | Reduces false positives |
| 0.80 auto-commit, 0.60 minimum | Conservative thresholds per Doc 14 |
| Never log message content | Doc 14 §1: log only metadata |
| Negated tech facts dropped entirely | "won't use X" ≠ "uses X" |

---

## Files Summary

| File | Purpose | Lines Est. |
|------|---------|-----------|
| `backend/extraction/__init__.py` | Package init | 5 |
| `backend/extraction/sensitive_filter.py` | PII/credential detection | ~60 |
| `backend/extraction/rule_based.py` | Regex patterns for tech/decisions/goals | ~150 |
| `backend/extraction/hypothetical_detector.py` | "What if" / negation filtering | ~50 |
| `backend/extraction/ner_extractor.py` | spaCy NER + dep parsing | ~100 |
| `backend/extraction/llm_extractor.py` | Ollama/Phi-4 structured extraction | ~120 |
| `backend/extraction/confidence_scorer.py` | Multi-pass merge + routing | ~80 |
| `backend/extraction/pipeline.py` | Main orchestrator | ~90 |

**Total: 8 files, ~655 lines.**

---

> **Next: Plan 03 — Knowledge Graph & Core Services** (graph ops, conflict resolution, decay, consolidation, workspace service)
