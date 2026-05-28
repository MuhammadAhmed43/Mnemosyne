"""Tests for ConflictService._detect_choice_change (the "change of plans" detector).

Covers the four behaviours that matter:
  - a same-category tech switch WITH a switch cue flags a non-auto-resolvable VERSION_FORK
  - a cross-category (polyglot) combo does NOT flag, even with a cue
  - repeating the same tech does NOT flag
  - a same-category switch WITHOUT a cue does NOT flag (avoids polyglot false positives)
"""

from __future__ import annotations

from backend.models.enums import ConflictType, NodeType
from backend.models.memory_node import MemoryNode


def _commit(container, ws: str, content: str, node_type: NodeType = NodeType.DECISION) -> MemoryNode:
    node = MemoryNode(workspace_id=ws, node_type=node_type, content=content)
    container.node_repo(ws).create(node)
    return node


def _choice_conflicts(found):
    return [c for c in found if c.conflict_type == ConflictType.VERSION_FORK]


def test_language_switch_with_cue_flags(container, workspace):
    ws = workspace.id
    svc = container.conflict_service(ws)
    _commit(container, ws, "Let's build the NUST cafeteria website in Python")
    new = _commit(container, ws, "Change of plans, I'll use Go for the cafeteria website")

    found = _choice_conflicts(svc.detect_conflicts(ws, new))

    assert len(found) == 1, "Python -> Go switch should raise one version_fork conflict"
    c = found[0]
    assert c.node_b_id == new.id and c.node_a_id != new.id
    assert c.auto_resolvable is False, "change-of-plans conflicts must stay pending for the user"


def test_polyglot_different_categories_does_not_flag(container, workspace):
    ws = workspace.id
    svc = container.conflict_service(ws)
    _commit(container, ws, "Build the backend in Python")
    # 'actually' is a switch cue, but React (frontend) vs Python (language) are
    # different categories -> a legitimate polyglot stack, not a contradiction.
    new = _commit(container, ws, "Actually, let's also use React for the frontend")

    assert _choice_conflicts(svc.detect_conflicts(ws, new)) == []


def test_same_tech_repeated_does_not_flag(container, workspace):
    ws = workspace.id
    svc = container.conflict_service(ws)
    _commit(container, ws, "We'll use Python for the cafeteria site")
    new = _commit(container, ws, "Change of plans — actually let's stick with Python")

    assert _choice_conflicts(svc.detect_conflicts(ws, new)) == []


def test_same_category_switch_without_cue_does_not_flag(container, workspace):
    ws = workspace.id
    svc = container.conflict_service(ws)
    _commit(container, ws, "Uses Python", node_type=NodeType.TECHNICAL_FACT)
    # No switch cue -> treated as a coexisting (polyglot) fact, not a switch.
    new = _commit(container, ws, "Uses Go", node_type=NodeType.TECHNICAL_FACT)

    assert _choice_conflicts(svc.detect_conflicts(ws, new)) == []
