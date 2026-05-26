"""Filter hypothetical / negated statements (Doc 14 §3).

"What if we used MongoDB?" must never become a TECHNICAL_FACT. We heavily
penalize hypothetical-context candidates and drop negated tech facts entirely.
"""

from __future__ import annotations

import re

from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

HYPOTHETICAL_MARKERS = re.compile(
    r"\b(?:what if|imagine if|suppose we|could we|we might|"
    r"one option is|alternatively|we could consider|theoretically|"
    r"just brainstorming|hypothetically|maybe we should|"
    r"have you considered|another approach|what about)\b",
    re.IGNORECASE,
)

NEGATION_MARKERS = re.compile(
    r"\b(?:won'?t|will not|do(?:es)?n'?t|don'?t|did ?n'?t|"
    r"not going to|not (?:gonna|using|use)|aren'?t|isn'?t|never going to|"
    r"rejected|ruled out|decided against|dropped|removed|abandoned|scrapped|"
    r"that was wrong|incorrect|no longer)\b",
    re.IGNORECASE,
)


# Suggestion/listing phrasing — the AI proposing options ("you could use X", "such
# as", "options include") must not become a committed fact. "We use X" is fine.
SUGGESTION_MARKERS = re.compile(
    r"\b(?:you\s+(?:could|can|might|may)\s+(?:use|try|go\s+with|pick|consider)|"
    r"could\s+use|might\s+use|consider(?:ing)?\s+using|"
    r"options?\s+(?:include|are)|such\s+as|for\s+example|for\s+instance|e\.g\.|"
    r"alternatively|popular\s+(?:choices|options|tools)|"
    r"(?:i'?d\s+)?recommend(?:ed|ation)?|things?\s+like|a\s+(?:few|couple|number)\s+of\s+options)\b",
    re.IGNORECASE,
)


def is_hypothetical(text: str) -> bool:
    return bool(HYPOTHETICAL_MARKERS.search(text))


def is_suggested(text: str, entity: str) -> bool:
    return _near(text, entity, SUGGESTION_MARKERS)


def _near(text: str, entity: str, pattern: re.Pattern[str]) -> bool:
    """True if `pattern` matches in a window around `entity` in `text`."""
    if not entity:
        return False
    pos = text.lower().find(entity.lower())
    if pos == -1:
        return False
    window = text[max(0, pos - 80) : pos + len(entity) + 40]
    return bool(pattern.search(window))


def is_negated(text: str, entity: str) -> bool:
    return _near(text, entity, NEGATION_MARKERS)


def is_hypothetical_near(text: str, entity: str) -> bool:
    return _near(text, entity, HYPOTHETICAL_MARKERS)


def filter_hypotheticals(
    candidates: list[ExtractionCandidate], source_text: str = ""
) -> list[ExtractionCandidate]:
    """Filter hypotheticals/negations. `source_text` (the full turn) is the
    authoritative context — a candidate's own evidence may lack it (e.g. NER
    tech facts carry only 'entity_ruler:TECH'), so the hypothetical/negation
    context must be checked against the full source, windowed around the value."""
    kept: list[ExtractionCandidate] = []
    for c in candidates:
        ctx = source_text or f"{c.evidence}\n{c.content}"
        value = str(c.structured_data.get("value", ""))

        if c.node_type == NodeType.TECHNICAL_FACT:
            # Tech facts must not come from a negated, hypothetical, or merely
            # *suggested* context (the AI listing options ≠ the user committing).
            if value and (is_negated(ctx, value) or is_hypothetical_near(ctx, value) or is_suggested(ctx, value)):
                continue
        elif is_hypothetical(c.content) or is_hypothetical(c.evidence):
            c.confidence *= 0.3  # soft penalty for non-tech hypotheticals

        kept.append(c)
    return kept
