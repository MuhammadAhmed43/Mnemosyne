"""Unit tests for the extraction pieces (pure logic, no DB)."""

from __future__ import annotations

import pytest

from backend.extraction.confidence_scorer import ConfidenceScorer
from backend.extraction.hypothetical_detector import filter_hypotheticals
from backend.extraction.importance_scorer import compute_initial_importance
from backend.extraction.rule_based import RuleBasedExtractor
from backend.extraction.sensitive_filter import contains_sensitive_data
from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate


@pytest.mark.parametrize(
    "text",
    [
        "sk-abc123def456ghi789jkl012mno345pqr",
        "AKIAIOSFODNN7EXAMPLE",
        "123-45-6789",
        "postgresql://u:p@localhost/db",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_sensitive_detected(text):
    assert contains_sensitive_data(text).is_sensitive


def test_sensitive_clean_passes():
    assert not contains_sensitive_data("We use exponential backoff for retries").is_sensitive


class TestRuleBased:
    ex = RuleBasedExtractor()

    def test_known_tech_high_confidence(self):
        res = self.ex.extract("We use FastAPI and PostgreSQL", "ok")
        techs = {r.structured_data["value"] for r in res if r.node_type == NodeType.TECHNICAL_FACT}
        assert {"FastAPI", "PostgreSQL"} <= techs
        assert all(r.confidence == 0.90 for r in res if r.node_type == NodeType.TECHNICAL_FACT)

    def test_no_pronoun_capture(self):
        res = self.ex.extract("because we need full-text search", "")
        assert "we" not in {r.structured_data.get("value", "").lower() for r in res}

    def test_decision_and_goal(self):
        res = self.ex.extract("We decided to drop offline mode. Our goal is to ship Friday.", "")
        kinds = {r.node_type for r in res}
        assert NodeType.DECISION in kinds and NodeType.GOAL in kinds


def test_hypothetical_penalized():
    ex = RuleBasedExtractor()
    out = filter_hypotheticals(ex.extract("What if we used MongoDB instead?", ""))
    mongo = [r for r in out if r.structured_data.get("value") == "MongoDB"]
    assert all(r.confidence < 0.4 for r in mongo)


def test_negated_tech_dropped():
    ex = RuleBasedExtractor()
    out = filter_hypotheticals(ex.extract("We dropped Cassandra from the stack.", ""))
    assert not [r for r in out if r.structured_data.get("value") == "Cassandra"]


class TestConfidenceScorer:
    sc = ConfidenceScorer()

    def test_single_rule_tech_stays_auto_commit(self):
        c = ExtractionCandidate(node_type=NodeType.TECHNICAL_FACT, content="Uses FastAPI",
                                structured_data={"value": "FastAPI"}, confidence=0.90, source_pass="rule_based")
        merged = self.sc.merge_candidates([c])
        assert merged[0].confidence >= 0.80  # the Doc 06 §3.1 conflict fix

    def test_corroboration_boost(self):
        a = ExtractionCandidate(node_type=NodeType.TECHNICAL_FACT, content="Uses Redis",
                                structured_data={"value": "Redis"}, confidence=0.90, source_pass="rule_based")
        b = ExtractionCandidate(node_type=NodeType.TECHNICAL_FACT, content="Uses Redis",
                                structured_data={"value": "Redis"}, confidence=0.68, source_pass="ner")
        merged = self.sc.merge_candidates([a, b])
        assert merged[0].confidence > 0.90

    def test_routing(self):
        cands = [
            ExtractionCandidate(node_type=NodeType.GOAL, content="ship", confidence=0.9, source_pass="rule_based"),
            ExtractionCandidate(node_type=NodeType.PROBLEM, content="bug maybe", confidence=0.66, source_pass="ner"),
            ExtractionCandidate(node_type=NodeType.ENTITY, content="noise", confidence=0.5, source_pass="ner"),
        ]
        routed = self.sc.route_candidates(cands)
        assert len(routed["auto_commit"]) == 1
        assert len(routed["pending_review"]) == 1
        assert len(routed["discarded"]) == 1


def test_importance_ordering():
    dec = compute_initial_importance(NodeType.DECISION, "We decided to launch", 0.9, "claude")
    task = compute_initial_importance(NodeType.TASK, "fix typo", 0.7, "claude")
    manual = compute_initial_importance(NodeType.ENTITY, "Dr. Chen", 1.0, "manual")
    assert manual >= 0.9 and dec > task
