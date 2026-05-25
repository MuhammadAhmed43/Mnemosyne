"""Pass 2 — spaCy NER + dependency parsing (Doc 06 §4).

Degrades gracefully: if the spaCy model isn't installed, NER is skipped (the
pipeline still runs on rules + LLM). Doc 11 risk row: "spaCy model missing ->
NER pass skipped".
"""

from __future__ import annotations

import logging

from backend.extraction.rule_based import TECH_ENTITIES
from backend.models.enums import NodeType
from backend.models.extraction import ExtractionCandidate

logger = logging.getLogger("mnemosyne.extraction")

DEADLINE_WORDS = ("deadline", "due", "by", "before", "launch")


def _useful_entity(text: str) -> bool:
    """Filter the low-value PERSON/ORG/PRODUCT entities spaCy's small model emits
    in bulk (each one becomes a pending item). Keep proper-noun-looking names;
    drop short fragments and single all-lowercase words ('jargon', 'metadata',
    'briefs') that are common nouns mislabeled as entities."""
    t = text.strip()
    if len(t) < 3:
        return False
    # A genuine named entity is usually capitalized, multi-word, or has a dot
    # (e.g. "Copy.ai"). A lone all-lowercase token almost never is.
    if " " not in t and "." not in t and t == t.lower():
        return False
    return True


class NERExtractor:
    def __init__(self, model: str = "en_core_web_sm"):
        self.nlp = None
        try:
            import spacy  # noqa: PLC0415

            self.nlp = spacy.load(model, disable=["lemmatizer"])
            ruler = self.nlp.add_pipe("entity_ruler", before="ner")
            ruler.add_patterns([{"label": "TECH", "pattern": t} for t in TECH_ENTITIES])
        except Exception as e:  # noqa: BLE001 - missing model/library -> degrade
            logger.warning("spaCy NER unavailable (%s) - NER pass disabled", type(e).__name__)

    @property
    def available(self) -> bool:
        return self.nlp is not None

    def extract(self, user_msg: str, ai_msg: str) -> list[ExtractionCandidate]:
        if self.nlp is None:
            return []
        doc = self.nlp(f"{user_msg}\n{ai_msg}")
        out: list[ExtractionCandidate] = []

        for ent in doc.ents:
            label = ent.label_
            if label in ("PERSON", "ORG", "PRODUCT") and not _useful_entity(ent.text):
                continue  # drop low-value / mislabeled common-noun entities
            # Bare entities are low value and extremely noisy (the AI naming a
            # dozen tools/projects -> a dozen pending items). Score them BELOW the
            # min-confidence floor so a single mention is discarded; only entities
            # corroborated by another pass (+0.08 each) survive to review.
            if label == "PERSON":
                out.append(self._entity(ent.text, "person", 0.55, "PERSON"))
            elif label == "ORG":
                out.append(self._entity(ent.text, "org", 0.52, "ORG"))
            elif label == "PRODUCT":
                out.append(self._entity(ent.text, "product", 0.50, "PRODUCT"))
            elif label == "TECH":
                out.append(
                    ExtractionCandidate(
                        node_type=NodeType.TECHNICAL_FACT,
                        content=f"Uses {ent.text}",
                        structured_data={"entity": "tech", "value": ent.text},
                        confidence=0.68,
                        source_pass="ner",
                        evidence="entity_ruler:TECH",
                    )
                )
            elif label in ("DATE", "TIME"):
                sent = ent.sent.text
                if any(w in sent.lower() for w in DEADLINE_WORDS):
                    out.append(
                        ExtractionCandidate(
                            node_type=NodeType.TASK,
                            content=sent.strip(),
                            structured_data={"due_date": ent.text},
                            confidence=0.65,
                            source_pass="ner",
                            evidence="deadline_context",
                        )
                    )
            elif label == "MONEY":
                out.append(
                    ExtractionCandidate(
                        node_type=NodeType.TECHNICAL_FACT,
                        content=f"Budget/cost reference: {ent.text}",
                        structured_data={"entity": "budget", "value": ent.text, "category": "financial"},
                        confidence=0.62,
                        source_pass="ner",
                        evidence="spaCy:MONEY",
                    )
                )

        return out

    @staticmethod
    def _entity(text: str, etype: str, conf: float, label: str) -> ExtractionCandidate:
        return ExtractionCandidate(
            node_type=NodeType.ENTITY,
            content=text,
            structured_data={"entity_type": etype},
            confidence=conf,
            source_pass="ner",
            evidence=f"spaCy:{label}",
        )
