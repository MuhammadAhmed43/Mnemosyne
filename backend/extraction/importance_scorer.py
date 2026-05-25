"""Initial importance scoring for committed nodes (Doc 04 §9)."""

from __future__ import annotations

from backend.models.enums import NodeType

TYPE_WEIGHTS = {
    NodeType.DECISION: 0.80,
    NodeType.GOAL: 0.75,
    NodeType.PROBLEM: 0.70,
    NodeType.PREFERENCE: 0.70,
    NodeType.TECHNICAL_FACT: 0.65,
    NodeType.EVENT: 0.60,
    NodeType.ENTITY: 0.55,
    NodeType.TASK: 0.50,
    NodeType.INSIGHT: 0.60,
    NodeType.CONSTRAINT: 0.65,
    NodeType.HYPOTHESIS: 0.50,
    NodeType.OPEN_QUESTION: 0.50,
    NodeType.RELATIONSHIP: 0.55,
    NodeType.WORKSPACE_SUMMARY: 0.40,
    NodeType.USER_NOTE: 0.90,
}

HIGH_IMPORTANCE_KEYWORDS = (
    "never", "always", "critical", "must", "blocked",
    "decided", "final", "confirmed", "deadline", "launch",
    "breaking", "urgent", "production", "security",
)


def compute_initial_importance(
    node_type: NodeType,
    content: str,
    extraction_confidence: float,
    source_platform: str,
) -> float:
    score = TYPE_WEIGHTS.get(node_type, 0.5)
    # Confidence modifier: scales the score into [0.7, 1.0] x base
    score *= 0.7 + 0.3 * extraction_confidence
    # Keyword boosters
    low = content.lower()
    hits = sum(1 for k in HIGH_IMPORTANCE_KEYWORDS if k in low)
    score = min(1.0, score + 0.05 * hits)
    # Manual entries are inherently important
    if source_platform == "manual":
        score = max(score, 0.9)
    return round(min(score, 1.0), 3)
