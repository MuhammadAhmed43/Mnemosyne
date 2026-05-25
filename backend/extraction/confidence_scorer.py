"""Merge multi-pass candidates + final confidence scoring + routing (Doc 06 §6).

DEVIATION from Plan 02 (authorized): the plan down-weighted single-pass
candidates by a per-pass weight, which dropped rule-based tech facts from 0.90
to ~0.60 and contradicted Doc 06 §3.1 (those are auto-commit eligible). Instead:
each extractor already sets a per-candidate confidence reflecting reliability;
agreement across passes only ADDS confidence (corroboration), it never subtracts.
Merged base = the strongest pass's confidence, then additive boosts.
"""

from __future__ import annotations

from collections import defaultdict

from backend.models.extraction import ExtractionCandidate

# Doc 14 §3 thresholds
AUTO_COMMIT_THRESHOLD = 0.80
MIN_CONFIDENCE = 0.60

# Doc 06 §6 boosts
CORROBORATION_BOOST = 0.08  # per additional corroborating pass
CONTEXT_BOOST = 0.05  # workspace context corroborates (applied by pipeline)
EXPLICIT_LANGUAGE_BOOST = 0.10
MAX_CONFIDENCE = 0.98  # never absolute certainty

EXPLICIT_MARKERS = (
    "decided", "confirmed", "agreed", "committed", "finalized",
    "resolved", "settled", "concluded", "must", "always", "never",
)


def _has_explicit_marker(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in EXPLICIT_MARKERS)


class ConfidenceScorer:
    def merge_candidates(
        self, candidates: list[ExtractionCandidate], min_confidence: float = MIN_CONFIDENCE
    ) -> list[ExtractionCandidate]:
        groups = self._group_similar(candidates)
        merged: list[ExtractionCandidate] = []

        for group in groups.values():
            best = max(group, key=lambda c: c.confidence)
            passes = sorted({c.source_pass for c in group})
            best.corroborated_by = [p for p in passes if p != best.source_pass]

            score = best.confidence
            score += len(best.corroborated_by) * CORROBORATION_BOOST
            if _has_explicit_marker(f"{best.content} {best.evidence}"):
                score += EXPLICIT_LANGUAGE_BOOST
            best.confidence = round(min(score, MAX_CONFIDENCE), 3)
            best.source_pass = "+".join(passes)
            merged.append(best)

        return [c for c in merged if c.confidence >= min_confidence]

    def apply_context_boost(self, candidate: ExtractionCandidate, corroborates: bool) -> None:
        """Pipeline-level boost when workspace context agrees (Doc 06 §6)."""
        if corroborates:
            candidate.confidence = round(min(candidate.confidence + CONTEXT_BOOST, MAX_CONFIDENCE), 3)

    def route_candidates(
        self,
        candidates: list[ExtractionCandidate],
        auto_commit_threshold: float = AUTO_COMMIT_THRESHOLD,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> dict[str, list]:
        # Guard against an inverted config (min above auto): clamp so the bands
        # stay well-ordered and routing never silently drops everything.
        min_confidence = min(min_confidence, auto_commit_threshold)
        out: dict[str, list[ExtractionCandidate]] = {
            "auto_commit": [],
            "pending_review": [],
            "discarded": [],
        }
        for c in candidates:
            if c.confidence >= auto_commit_threshold:
                out["auto_commit"].append(c)
            elif c.confidence >= min_confidence:
                out["pending_review"].append(c)
            else:
                out["discarded"].append(c)
        return out

    @staticmethod
    def _group_similar(
        candidates: list[ExtractionCandidate],
    ) -> dict[tuple, list[ExtractionCandidate]]:
        groups: dict[tuple, list[ExtractionCandidate]] = defaultdict(list)
        for c in candidates:
            words = tuple(sorted(w.lower() for w in c.content.split() if len(w) > 3)[:5])
            groups[(c.node_type, words)].append(c)
        return groups
