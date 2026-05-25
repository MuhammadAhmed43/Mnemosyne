"""Intent classification to weight retrieval sources (Doc 10 §6, Plan 05).

Keyword-based category -> per-source weight multipliers. The semantic query
vector is not precomputed here; RetrievalService embeds the hint directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class IntentCategory(str, Enum):
    CONTINUE_WORK = "continue_work"
    DEBUG = "debug"
    DESIGN = "design"
    REVIEW = "review"
    BRAINSTORM = "brainstorm"
    GENERAL = "general"


INTENT_SIGNALS = {
    IntentCategory.DEBUG: ["error", "bug", "crash", "failing", "doesn't work", "broken",
                           "exception", "stack trace", "debug", "fix", "issue"],
    IntentCategory.DESIGN: ["architect", "design", "structure", "pattern", "approach",
                            "how should", "best way", "refactor", "redesign"],
    IntentCategory.REVIEW: ["review", "check", "look at", "feedback", "improve", "optimize"],
    IntentCategory.BRAINSTORM: ["ideas", "brainstorm", "options", "alternatives", "what if",
                                "possibilities", "suggest", "creative"],
    IntentCategory.CONTINUE_WORK: ["continue", "pick up", "left off", "last time", "yesterday",
                                   "where were we", "resume", "back to"],
}

_BASE_WEIGHTS = {"goals": 1.0, "decisions": 1.0, "problems": 0.8, "semantic": 1.0, "high_importance": 0.7}

_OVERRIDES = {
    IntentCategory.DEBUG: {"problems": 1.5, "semantic": 1.3},
    IntentCategory.DESIGN: {"decisions": 1.4, "goals": 1.2},
    IntentCategory.CONTINUE_WORK: {"decisions": 1.3, "problems": 1.2},
    IntentCategory.BRAINSTORM: {"goals": 1.3, "semantic": 0.8},
    IntentCategory.REVIEW: {"decisions": 1.2, "semantic": 1.2},
}


class IntentService:
    def classify(self, hint: Optional[str]) -> IntentCategory:
        if not hint:
            return IntentCategory.GENERAL
        low = hint.lower()
        scores = {
            intent: sum(1 for kw in kws if kw in low)
            for intent, kws in INTENT_SIGNALS.items()
        }
        scores = {k: v for k, v in scores.items() if v > 0}
        return max(scores, key=scores.get) if scores else IntentCategory.GENERAL

    def get_retrieval_weights(self, intent: IntentCategory) -> dict[str, float]:
        weights = dict(_BASE_WEIGHTS)
        weights.update(_OVERRIDES.get(intent, {}))
        return weights
