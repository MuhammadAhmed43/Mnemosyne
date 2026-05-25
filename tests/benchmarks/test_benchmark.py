"""Extraction quality benchmark (Doc 15 §4).

A seed labeled set (expandable toward the spec's 500 samples). Runs the
rule+NER+filter+scorer path (no Ollama in CI), measures recall of expected
node types and asserts ZERO forbidden extractions (hypotheticals/negations).
Without the LLM pass recall is naturally lower, so the bar reflects that;
precision is enforced strictly via the forbidden set.
"""

from __future__ import annotations

from backend.extraction.confidence_scorer import ConfidenceScorer
from backend.extraction.hypothetical_detector import filter_hypotheticals
from backend.extraction.ner_extractor import NERExtractor
from backend.extraction.rule_based import RuleBasedExtractor
from backend.models.enums import NodeType

# (user_text, ai_text, expected_types, forbidden_values)
SAMPLES = [
    ("We decided to use FastAPI for the backend", "Solid.", {NodeType.DECISION, NodeType.TECHNICAL_FACT}, set()),
    ("Our goal is to ship the beta by Friday", "Got it.", {NodeType.GOAL}, set()),
    ("The problem is the login keeps failing", "Let's debug.", {NodeType.PROBLEM}, set()),
    ("We chose PostgreSQL and Redis for storage", "ok", {NodeType.TECHNICAL_FACT}, set()),
    ("I prefer concise answers without fluff", "Understood.", {NodeType.PREFERENCE}, set()),
    ("We shipped the v1 release today", "Congrats!", {NodeType.EVENT}, set()),
    ("What if we used MongoDB instead?", "Could consider.", set(), {"MongoDB"}),
    ("We dropped Cassandra from the stack", "ok", set(), {"Cassandra"}),
    ("We decided to drop offline mode because of scope", "Makes sense.", {NodeType.DECISION}, set()),
    ("We're using Next.js and Vercel for the frontend", "Nice.", {NodeType.TECHNICAL_FACT}, set()),
    ("Our deadline is Sunday and we must finish auth", "ok", {NodeType.GOAL}, set()),
    ("We migrated to Docker and Kubernetes", "ok", {NodeType.TECHNICAL_FACT}, set()),
]

_rule = RuleBasedExtractor()
_ner = NERExtractor()
_scorer = ConfidenceScorer()


def _extract(user, ai):
    cands = filter_hypotheticals(_rule.extract(user, ai) + _ner.extract(user, ai), source_text=f"{user}\n{ai}")
    merged = _scorer.merge_candidates(cands)
    return merged


def test_extraction_quality():
    tp = fn = forbidden_hits = 0
    for user, ai, expected, forbidden in SAMPLES:
        cands = _extract(user, ai)
        got_types = {c.node_type for c in cands}
        got_values = {str(c.structured_data.get("value", "")) for c in cands}
        for t in expected:
            if t in got_types:
                tp += 1
            else:
                fn += 1
        forbidden_hits += len(forbidden & got_values)

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    print(f"\nbenchmark: recall={recall:.2%} (tp={tp} fn={fn}) forbidden_hits={forbidden_hits}")
    # Strict precision via forbidden set: hypotheticals/negations must never extract.
    assert forbidden_hits == 0, f"{forbidden_hits} forbidden extractions (hypothetical/negated)"
    # Recall bar without the LLM pass (rule+NER only).
    assert recall >= 0.6, f"recall {recall:.2%} below 0.60 floor (rule+NER, no Ollama)"
