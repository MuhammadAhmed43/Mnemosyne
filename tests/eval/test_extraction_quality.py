"""Extraction quality eval — measures recall + precision against labeled cases.

Run as a report:    python tests/eval/test_extraction_quality.py
Run as a CI gate:   pytest tests/eval/

Evaluates the DETERMINISTIC pipeline (rules + spaCy NER + idea pass + scorer;
LLM pass disabled), so results are reproducible. The optional Ollama pass only
adds extractions on top of this baseline.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timezone

# Make this importable both under pytest and as a direct script: ensure the repo
# root (for `backend`) and this dir (for `cases`) are on sys.path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from backend.config import MnemosyneConfig  # noqa: E402
from backend.extraction.pipeline import ExtractionPipeline  # noqa: E402
from backend.models.capture import CaptureRecord  # noqa: E402
from backend.models.enums import Platform  # noqa: E402
from backend.utils.time import now_utc  # noqa: E402
from cases import CASES  # noqa: E402

# Node types whose content asserts a "fact" — used for precision (expect_absent).
_FACTUAL_TYPES = {"decision", "goal", "technical_fact", "preference", "event"}

# CI thresholds. Set below current measured performance so genuine regressions
# fail the build without being flaky. Tighten as the pipeline improves.
MIN_RECALL = 0.80
MAX_ABSENT_VIOLATIONS = 0


def _candidates(pipe: ExtractionPipeline, case: dict) -> list:
    """All extracted (committed + pending) candidates for a case, LLM disabled."""
    rec = CaptureRecord(
        session_id="eval", platform=Platform.CHATGPT, workspace_id="eval",
        user_message=case["user"], ai_response=case["ai"],
        timestamp=now_utc().replace(tzinfo=timezone.utc),
    )
    result = asyncio.run(pipe.run(rec, llm_enabled=False))
    return list(result.to_commit) + list(result.pending_review)


def _matches(cand, expected: dict) -> bool:
    if cand.node_type.value != expected["type"]:
        return False
    content = cand.content.lower()
    return all(kw.lower() in content for kw in expected.get("contains", []))


def evaluate(verbose: bool = False) -> dict:
    pipe = ExtractionPipeline(MnemosyneConfig())
    tp = fn = 0
    absent_violations: list[str] = []
    empty_violations: list[str] = []
    total_predicted = 0

    for case in CASES:
        cands = _candidates(pipe, case)
        total_predicted += len(cands)

        # Recall: each expected extraction should be matched by some candidate.
        case_hits = []
        for exp in case.get("expect", []):
            if any(_matches(c, exp) for c in cands):
                tp += 1
                case_hits.append(f"OK   {exp['type']}:{exp.get('contains')}")
            else:
                fn += 1
                case_hits.append(f"MISS {exp['type']}:{exp.get('contains')}")

        # Precision: forbidden terms must not appear in factual candidates.
        for term in case.get("expect_absent", []):
            if any(term.lower() in c.content.lower() for c in cands if c.node_type.value in _FACTUAL_TYPES):
                absent_violations.append(f"{case['name']}: leaked '{term}'")
                case_hits.append(f"LEAK '{term}'")

        if case.get("expect_empty") and cands:
            empty_violations.append(f"{case['name']}: expected empty, got {len(cands)}")
            case_hits.append(f"NOT EMPTY ({len(cands)})")

        if verbose:
            print(f"\n[{case['name']}]")
            for c in cands:
                print(f"    - {c.node_type.value:15} {c.confidence:.2f}  {c.content[:70]}")
            for h in case_hits:
                print(f"  {h}")

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    metrics = {
        "recall": round(recall, 3),
        "expected_total": tp + fn,
        "matched": tp,
        "absent_violations": absent_violations,
        "empty_violations": empty_violations,
        "total_predicted": total_predicted,
        "noise_ratio": round(total_predicted / max(1, tp + fn), 2),
    }
    return metrics


def test_extraction_recall_meets_threshold():
    m = evaluate()
    assert m["recall"] >= MIN_RECALL, f"recall {m['recall']} < {MIN_RECALL} (matched {m['matched']}/{m['expected_total']})"


def test_no_hypothetical_or_negation_leaks():
    m = evaluate()
    assert len(m["absent_violations"]) <= MAX_ABSENT_VIOLATIONS, m["absent_violations"]
    assert not m["empty_violations"], m["empty_violations"]


if __name__ == "__main__":
    m = evaluate(verbose=True)
    print("\n" + "=" * 50)
    print(f"  recall:            {m['recall']}  ({m['matched']}/{m['expected_total']} expected extractions)")
    print(f"  absent violations: {len(m['absent_violations'])}  {m['absent_violations']}")
    print(f"  empty violations:  {len(m['empty_violations'])}  {m['empty_violations']}")
    print(f"  predicted total:   {m['total_predicted']}  (noise ratio {m['noise_ratio']}x expected)")
    print("=" * 50)
