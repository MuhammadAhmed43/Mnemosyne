"""3-pass extraction orchestrator (Doc 06, Doc 14).

Order: sensitive filter -> trivial check -> rule pass -> NER pass ->
(gated) LLM pass -> hypothetical/negation filter -> merge + score -> route.

Synchronous passes are cheap; only the optional LLM pass awaits. The pipeline
produces routed *candidates*; the service layer commits them.
"""

from __future__ import annotations

import time

from backend.config import MnemosyneConfig
from backend.extraction.confidence_scorer import ConfidenceScorer
from backend.extraction.hypothetical_detector import filter_hypotheticals
from backend.extraction.idea_extractor import IdeaExtractor
from backend.extraction.llm_extractor import LLMExtractor
from backend.extraction.ner_extractor import NERExtractor
from backend.extraction.rule_based import RuleBasedExtractor
from backend.extraction.sensitive_filter import (
    check_custom_blocked_terms,
    contains_sensitive_data,
)
from backend.extraction.confidence_scorer import AUTO_COMMIT_THRESHOLD, MIN_CONFIDENCE
from backend.models.capture import CaptureRecord
from backend.models.extraction import ExtractionResult

TRIVIAL_MIN_CHARS = 50  # Doc 10 §2


class ExtractionPipeline:
    def __init__(self, config: MnemosyneConfig):
        self.config = config
        self.rule_based = RuleBasedExtractor()
        self.ner = NERExtractor()
        self.idea = IdeaExtractor()
        self.llm = LLMExtractor(config.ollama_url, config.ollama_model)
        self.scorer = ConfidenceScorer()

    async def run(
        self,
        capture: CaptureRecord,
        workspace_summary: str = "",
        blocked_terms: list[str] | None = None,
        auto_commit_threshold: float = AUTO_COMMIT_THRESHOLD,
        min_confidence: float = MIN_CONFIDENCE,
        llm_enabled: bool = True,
    ) -> ExtractionResult:
        start = time.monotonic()
        user_msg, ai_msg = capture.user_message, capture.ai_response
        combined = f"{user_msg}\n{ai_msg}"

        def done(reason: str | None = None, **buckets) -> ExtractionResult:
            return ExtractionResult(
                capture_id=capture.id,
                skipped=reason is not None,
                skip_reason=reason,
                duration_ms=int((time.monotonic() - start) * 1000),
                **buckets,
            )

        # Gate 1: sensitive data (Doc 14 §1 — first, before anything)
        if contains_sensitive_data(combined).is_sensitive:
            return done("sensitive_data")
        if blocked_terms and check_custom_blocked_terms(combined, blocked_terms).is_sensitive:
            return done("custom_blocked_term")

        # Gate 2: trivial content (Doc 10 §2)
        if len(combined.strip()) < TRIVIAL_MIN_CHARS:
            return done("trivial")

        # Pass 1 + Pass 2 (always available)
        rule_candidates = self.rule_based.extract(user_msg, ai_msg)
        ner_candidates = self.ner.extract(user_msg, ai_msg)

        # Idea pass: capture an explored idea/concept as an INSIGHT. Runs always
        # (cheap regex); bypasses the hypothetical filter below because the user
        # explicitly asked the AI to expand on it — it's not speculation.
        idea_candidates = self.idea.extract(user_msg, ai_msg)

        # Pass 3 — LLM reasoning. Runs on every substantial turn when enabled
        # (we're already past the trivial gate). `llm.extract()` self-skips
        # instantly when Ollama isn't running, so this is free for users without
        # it; for users who have it, it makes extraction phrasing-robust (catches
        # what brittle rules miss). Rules + NER remain the deterministic floor.
        llm_candidates = []
        if llm_enabled:
            llm_candidates = await self.llm.extract(user_msg, ai_msg, workspace_summary)

        # Filter hypotheticals/negations (against the full turn), then re-add the
        # idea candidates, merge + score, route.
        all_candidates = filter_hypotheticals(
            rule_candidates + ner_candidates + llm_candidates, source_text=combined
        ) + idea_candidates
        merged = self.scorer.merge_candidates(all_candidates, min_confidence=min_confidence)
        routed = self.scorer.route_candidates(
            merged, auto_commit_threshold=auto_commit_threshold, min_confidence=min_confidence
        )

        return done(
            to_commit=routed["auto_commit"],
            pending_review=routed["pending_review"],
            discarded=routed["discarded"],
        )
