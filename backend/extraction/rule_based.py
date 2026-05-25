"""Pass 1 — fast, high-precision regex extraction (Doc 06 §3). Always available."""

from __future__ import annotations

import re

from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

# Representative tech vocabulary (Doc 06 §3.1 — expandable).
TECH_ENTITIES = [
    "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt", "Remix",
    "FastAPI", "Django", "Flask", "Express", "Spring", "Rails", "Laravel",
    "PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis", "Cassandra", "DynamoDB",
    "Supabase", "Firebase", "Qdrant", "Pinecone", "Elasticsearch",
    "Docker", "Kubernetes", "Terraform", "Ansible",
    "AWS", "GCP", "Azure", "Vercel", "Railway", "Render", "Fly.io", "Netlify",
    "Python", "TypeScript", "JavaScript", "Rust", "Go", "Java", "Kotlin", "Swift", "Ruby",
    "TensorFlow", "PyTorch", "scikit-learn", "spaCy", "LangChain", "LangGraph",
    "GPT-4", "GPT-5", "Claude", "Gemini", "Llama", "Mistral", "Phi-4", "Qwen", "Ollama",
    "Stripe", "Paddle", "Twilio", "GraphQL", "gRPC", "Kafka", "RabbitMQ",
]

# Direct match of known tech names. CASE-SENSITIVE on purpose: tech is normally
# written in canonical case ("FastAPI", "PostgreSQL", "Go"), and case-sensitivity
# kills false positives like the verb "go" or "rust". Precision > recall here
# because these are auto-commit-eligible at 0.90 (Doc 14 §3: false positives are
# worse than false negatives).
TECH_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(TECH_ENTITIES, key=len, reverse=True)) + r")\b"
)

# Contextual capture for NOVEL techs not in the list ("we switched to Frobnicator").
TECH_CONTEXT = re.compile(
    r"(?:(?:we|i|our team)\s+)?"
    r"(?:use|using|built with|running on|switched to|migrated to|chose|adopted|deployed on)\s+"
    r"([A-Za-z0-9.\-+]+(?:\s+\d+[.\d]*)?)",
    re.IGNORECASE,
)

# Common words the contextual capture must never treat as a technology.
_CONTEXT_STOPWORDS = {
    "we", "i", "it", "this", "that", "the", "a", "an", "them", "these", "those",
    "our", "my", "your", "his", "her", "their", "both", "one", "two", "all",
}

DECISION_TRIGGERS = re.compile(
    r"(?:we\s+)?(?:decided|agreed|went with|chose|committed to|"
    r"settled on|concluded|determined|resolved to|"
    r"will\s+(?:go with|use|implement|build|switch))",
    re.IGNORECASE,
)

# Firm first-person commitments ("let's work with X", "I'll go with X"). These
# are real decisions the user expects in memory, so they score high enough to
# auto-commit (0.82 >= the 0.80 threshold) rather than languish in review.
# Firm commitments -> DECISION (a choice has been made).
CHOICE_TRIGGERS = re.compile(
    r"(?:let'?s|let us|i'?ll|we'?ll|i'?m going to|we'?re going to|i am going to)\s+"
    r"(?:go with|work\s+(?:on|with)|use|build|start with|focus on|do|try|adopt|switch to|make)\b",
    re.IGNORECASE,
)

# Aspirational first-person intent -> GOAL (what the user is trying to do). Still
# scored to auto-commit: it's an explicit, direct statement worth remembering.
GOAL_INTENT_TRIGGERS = re.compile(
    r"(?:i want to|i'?d like to|i wanna|i plan to|i intend to|i'?m planning to|"
    r"i hope to|i aim to|i'?m trying to)\s+"
    r"(?:go with|work\s+(?:on|with)|use|build|start with|focus on|do|try|learn|explore|study|make|create|develop)\b",
    re.IGNORECASE,
)

GOAL_TRIGGERS = re.compile(
    r"(?:(?:my|our|the)\s+)?"
    r"(?:goal|objective|target|aim|plan|deadline|milestone|priority)\s+"
    r"(?:is|was|should be|will be)",
    re.IGNORECASE,
)

ACTION_GOALS = re.compile(
    r"(?:need to|have to|must|should|want to|going to|plan to|"
    r"trying to|working on|aiming to|hoping to)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

PROBLEM_TRIGGERS = re.compile(
    r"(?:the problem|the issue|struggling with|stuck on|blocked by|blocked on|blocker|"
    r"can'?t figure out|can'?t get|doesn'?t work|won'?t (?:work|build|compile|start)|"
    r"bug in|error with|keeps (?:failing|returning|crashing|throwing)|failing)",
    re.IGNORECASE,
)

PREFERENCE_TRIGGERS = re.compile(
    r"(?:i prefer|i like|i always|i never|i tend to|"
    r"my style|i want you to|please always|please don't|"
    r"don't (?:use|suggest|recommend))",
    re.IGNORECASE,
)

EVENT_TRIGGERS = re.compile(
    r"(?:we shipped|we launched|we deployed|we released|we completed|"
    r"we finished|we presented|we submitted|we merged|we published|"
    r"just shipped|just launched|just deployed|just released|"
    r"successfully (?:deployed|launched|shipped|completed)|"
    r"went live|pushed to production|milestone|breakthrough|achieved)",
    re.IGNORECASE,
)

RATIONALE_TRIGGERS = re.compile(
    r"(?:because|reason(?:\s*:|\s+is|\s+was)|since|due to|"
    r"to (?:avoid|prevent|reduce|improve))\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)

COMPLETION_TRIGGERS = re.compile(
    r"(?:completed|finished|shipped|launched|deployed|done with|wrapped up)\s+(.+?)(?:\.|$)|"
    r"(.+?)\s+(?:is done|is complete|is finished|is shipped|is live)",
    re.IGNORECASE,
)


class RuleBasedExtractor:
    """Pass 1: regex-based extraction (<50ms, zero dependencies)."""

    def extract(self, user_msg: str, ai_msg: str) -> list[ExtractionCandidate]:
        combined = f"{user_msg}\n{ai_msg}"
        out: list[ExtractionCandidate] = []
        seen_tech: set[str] = set()

        # Known techs (high precision, 0.90, auto-commit eligible per Doc 06 §3.1)
        for m in TECH_PATTERN.finditer(combined):
            value = m.group(1)
            if value.lower() in seen_tech:
                continue
            seen_tech.add(value.lower())
            out.append(
                ExtractionCandidate(
                    node_type=NodeType.TECHNICAL_FACT,
                    content=f"Uses {value}",
                    structured_data={"entity": "tech", "value": value},
                    confidence=0.90,
                    source_pass="rule_based",
                    evidence=self._sentence(combined, m.start()),
                )
            )

        # Novel techs via verb context. Guard: must be Title-case in source and
        # not a stopword (prevents capturing pronouns like "we"). Lower confidence.
        for m in TECH_CONTEXT.finditer(combined):
            value = m.group(1).strip()
            if (
                not value
                or value.lower() in seen_tech
                or value.lower() in _CONTEXT_STOPWORDS
                or not value[0].isupper()
            ):
                continue
            seen_tech.add(value.lower())
            out.append(
                ExtractionCandidate(
                    node_type=NodeType.TECHNICAL_FACT,
                    content=f"Uses {value}",
                    structured_data={"entity": "tech", "value": value},
                    confidence=0.75,
                    source_pass="rule_based",
                    evidence=self._sentence(combined, m.start()),
                )
            )

        for trig, ntype, conf in (
            (CHOICE_TRIGGERS, NodeType.DECISION, 0.82),
            (GOAL_INTENT_TRIGGERS, NodeType.GOAL, 0.82),
            (DECISION_TRIGGERS, NodeType.DECISION, 0.78),
            (GOAL_TRIGGERS, NodeType.GOAL, 0.72),
            (PROBLEM_TRIGGERS, NodeType.PROBLEM, 0.70),
            (PREFERENCE_TRIGGERS, NodeType.PREFERENCE, 0.68),
            (EVENT_TRIGGERS, NodeType.EVENT, 0.74),
        ):
            for m in trig.finditer(combined):
                sentence = self._sentence(combined, m.start())
                out.append(
                    ExtractionCandidate(
                        node_type=ntype,
                        content=sentence,
                        confidence=conf,
                        source_pass="rule_based",
                        evidence=sentence,
                    )
                )

        # Completion events (Doc 06 §3.3) — flag for GOAL -> COMPLETED handling
        for m in COMPLETION_TRIGGERS.finditer(combined):
            subject = (m.group(1) or m.group(2) or "").strip()
            if subject:
                out.append(
                    ExtractionCandidate(
                        node_type=NodeType.EVENT,
                        content=self._sentence(combined, m.start()),
                        structured_data={
                            "outcome": "positive",
                            "completed_subject": subject,
                            "triggers_goal_completion": True,
                        },
                        confidence=0.76,
                        source_pass="rule_based",
                        evidence="completion_trigger",
                    )
                )

        # Attach rationale to the most recent decision candidate (Doc 06 §3.2)
        rationale_match = RATIONALE_TRIGGERS.search(combined)
        if rationale_match:
            for c in reversed(out):
                if c.node_type == NodeType.DECISION:
                    c.structured_data["rationale"] = rationale_match.group(1).strip()
                    break

        return out

    @staticmethod
    def _sentence(text: str, pos: int) -> str:
        start = text.rfind(".", 0, pos)
        start = 0 if start == -1 else start + 1
        end = text.find(".", pos)
        end = len(text) if end == -1 else end + 1
        return text[start:end].strip()
