"""Idea / concept capture pass (the "I'm exploring an idea" workflow).

The rest of the pipeline is tuned for *decisions / goals / facts* — strong,
user-stated commitments. That misses the common case where the user is
brainstorming with the AI: they ask the AI to expand on a specific idea or
concept, the AI explains how it works, and the user wants that idea + its
workings remembered so a later chat can resume from it.

Signal: the user message shows elaboration / selection / learning intent ("tell
me more about X", "how would I build X", "explain X", "let's go with the second
one") AND the AI actually explained something substantial. When both hold we
capture an INSIGHT node — the idea and its gist — at auto-commit confidence,
because explicit engagement is a strong relevance signal.
"""

from __future__ import annotations

import re

from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

# The AI must have actually explained something (not a one-line reply) for the
# turn to be worth remembering as an idea.
IDEA_MIN_AI_CHARS = 200
# Explicit user engagement -> trustworthy enough to commit straight to memory.
IDEA_CONFIDENCE = 0.82

# Elaboration / selection / learning / info-seeking intent in the *user* message.
_IDEA_INTENT = re.compile(
    r"\b("
    r"tell me more|more about|explain|elaborate|go deeper|deep[- ]dive|expand on|"
    r"walk me through|break (?:this|it|that) down|give me (?:the )?(?:details?|a breakdown)|"
    r"details? (?:on|about|of)|"
    r"how (?:do|would|can|should|might) (?:i|we|you)|how does|how to|"
    r"what(?:'s| is| are)|"
    # info-seeking / brainstorming (these were producing only entity noise before)
    r"is there (?:a|an|any|some)|are there|"
    r"recommend|suggest|recommendation|"
    r"which (?:app|tool|tools|library|framework|service|option|approach|one|model)|"
    r"what(?:'s| is| are) the best|best (?:app|tool|way|approach|option|practice)|"
    r"looking for|options for|ideas for|any (?:apps|tools|ways|ideas)|"
    r"help me (?:build|create|design|plan|make|set up|figure)|"
    r"i (?:like|love|prefer|want|need|'?m looking|'?m interested in|'?ll go with)|"
    r"let'?s (?:go with|build|do|explore|use|try)|focus on|"
    r"the (?:first|second|third|fourth|fifth|last|next) (?:one|idea|option|approach)|"
    r"idea (?:#|number )?\d+"
    r")\b",
    re.IGNORECASE,
)

# Lead-in phrases stripped to recover the underlying topic the user asked about.
_LEADINS = re.compile(
    r"^\s*(?:can you |could you |would you |please |so |okay |ok |hey |hi |)*"
    r"(?:tell me more about|tell me about|more about|explain(?: to me)?(?: how| what| why)?|"
    r"elaborate on|expand on|walk me through|give me (?:the )?details? (?:on|about|of)?|"
    r"details? (?:on|about|of)|break (?:this|it|that) down|"
    r"how (?:do|would|can|should|might) (?:i|we|you)|how does|how to|"
    r"what(?:'s| is| are)(?: the| a| an)?|"
    r"i (?:like|love|prefer|want to build|want to go with|'?ll go with|'?m interested in)|"
    r"let'?s (?:go with|build|do|explore|use|try)|focus on)\s+",
    re.IGNORECASE,
)

# Filler opener sentences in AI replies that carry no information.
_FILLER_OPENER = re.compile(
    r"^(?:sure|great question|absolutely|of course|certainly|good question|"
    r"happy to help|let'?s dive in|here'?s)\b[^.!?]*[.!?]\s*",
    re.IGNORECASE,
)


def has_idea_intent(user_msg: str) -> bool:
    return bool(_IDEA_INTENT.search(user_msg or ""))


class IdeaExtractor:
    """Pass: capture an explored idea/concept as an INSIGHT (<1ms, regex only)."""

    def extract(self, user_msg: str, ai_msg: str) -> list[ExtractionCandidate]:
        u = (user_msg or "").strip()
        a = (ai_msg or "").strip()
        if not u or len(a) < IDEA_MIN_AI_CHARS or not has_idea_intent(u):
            return []

        topic = self._topic(u)
        gist = self._gist(a)
        content = f"Idea — {topic}: {gist}" if topic else f"Idea: {gist}"
        return [
            ExtractionCandidate(
                node_type=NodeType.INSIGHT,
                content=content[:1600],
                structured_data={"kind": "idea", "topic": topic, "source": "idea_capture"},
                confidence=IDEA_CONFIDENCE,
                source_pass="idea",
                evidence="idea_intent+substantive_answer",
            )
        ]

    def _topic(self, user_msg: str) -> str:
        t = _LEADINS.sub("", user_msg, count=1).strip(" ?.!,:")
        t = re.sub(r"\s+", " ", t)
        words = t.split()
        topic = " ".join(words[:12])[:90]
        # If stripping ate everything (e.g. the message was *only* a lead-in),
        # fall back to the raw message so we still have a label.
        return topic or " ".join(user_msg.split()[:12])[:90]

    @staticmethod
    def _gist(ai_msg: str) -> str:
        # Keep a meaningful chunk of "the working" (not just the first line) so the
        # idea is actually resumable later — capped so it stays a summary, not a
        # full transcript. Strips a leading filler sentence ("Great question! …").
        text = _FILLER_OPENER.sub("", ai_msg.strip(), count=1).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        gist = " ".join(sentences[:8]).strip()
        return (gist or text)[:1400]
