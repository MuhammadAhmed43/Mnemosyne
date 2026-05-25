# FIX — Plan 02: Extraction Pipeline
## Fix for C-03
---

## HOW TO USE THIS FILE
Apply this fix to the exact location shown. One function to modify.

---

## FIX C-03 — `_should_run_llm_pass()` missing 4th trigger condition
**File to edit:** `backend/extraction/pipeline.py`
**Function:** `_should_run_llm_pass(self, text, rule_candidates, ner_candidates)`

**Find the entire function (it ends with `return True`):**

```python
    def _should_run_llm_pass(
        self,
        text: str,
        rule_candidates: list,
        ner_candidates: list
    ) -> bool:
        """Doc 06 §5.1: Gate LLM pass — only run when truly needed."""
        # Has rule/NER already found goals or decisions?
        combined_candidates = rule_candidates + ner_candidates
        has_goals_or_decisions = any(
            c.node_type in (NodeType.GOAL, NodeType.DECISION)
            for c in combined_candidates
        )
        if has_goals_or_decisions:
            return False  # Already found key types — skip LLM

        # Turn must be > 3 sentences
        sentence_count = text.count('.') + text.count('!') + text.count('?')
        if sentence_count < 3:
            return False

        # Must contain first-person planning/preference language
        first_person = re.search(
            r'\b(?:I |we |my |our )(?:plan|want|need|going to|prefer|think|feel|decided)',
            text, re.IGNORECASE
        )
        if not first_person:
            return False

        return True
```

**Replace with:**

```python
    def _should_run_llm_pass(
        self,
        text: str,
        rule_candidates: list,
        ner_candidates: list
    ) -> bool:
        """Doc 06 §5.1: Gate LLM pass — only run when truly needed.

        Four conditions (all four must be checked — Doc 06 §5.1):
          1. Rule/NER already found goals or decisions → skip LLM
          2. Text is too short (< 3 sentences) → skip LLM
          3. No first-person planning language → skip LLM
          4. Multi-topic complexity: text covers >= 3 distinct cognitive
             categories simultaneously → RUN LLM (even if short/no first-person)
        """
        combined_candidates = rule_candidates + ner_candidates

        # Condition 1: rule/NER already caught key types — no need for LLM
        has_goals_or_decisions = any(
            c.node_type in (NodeType.GOAL, NodeType.DECISION)
            for c in combined_candidates
        )
        if has_goals_or_decisions:
            return False

        # Condition 4 (checked before 2 & 3 intentionally):
        # Multi-topic complexity — text simultaneously discusses multiple cognitive
        # categories. Short messages that pack in goals + tech + decisions in one turn
        # benefit most from LLM extraction. (Doc 06 §5.1 condition 4)
        candidate_types = {c.node_type for c in combined_candidates}
        MULTI_TOPIC_THRESHOLD = 3  # >= 3 distinct node types in one turn
        if len(candidate_types) >= MULTI_TOPIC_THRESHOLD:
            return True

        # Condition 2: too short for LLM to add value
        sentence_count = text.count('.') + text.count('!') + text.count('?')
        if sentence_count < 3:
            return False

        # Condition 3: no first-person planning/preference signal
        first_person = re.search(
            r'\b(?:I |we |my |our )(?:plan|want|need|going to|prefer|think|feel|decided)',
            text, re.IGNORECASE
        )
        if not first_person:
            return False

        return True
```

**Why:** Doc 06 §5.1 lists exactly four conditions that trigger the LLM pass. The original
plan omits condition 4: "Text discusses multiple complex topics." This matters for short,
dense messages like "We're using FastAPI, switching to Postgres, and the goal is to ship
by Friday" — the rule-based pass finds TECHNICAL_FACT and GOAL candidates, which are
different types, but `has_goals_or_decisions` fires and returns False before the multi-topic
check. The fix reorders the logic: the multi-topic check acts as an override that can force
the LLM pass even when condition 1 would otherwise skip it. This recovers the recall loss
for mixed-topic turns. (Ref: Doc 06 §5.1, C-03 conflict report)

---

## No other changes needed in Plan 02.
