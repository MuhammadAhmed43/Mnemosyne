"""Integration: full extraction pipeline + graph commit + retrieval + conflict flow."""

from __future__ import annotations

from datetime import timezone

from backend.models.capture import CaptureRecord
from backend.models.enums import NodeType, NodeStatus, Platform
from backend.models.extraction import ExtractionCandidate
from backend.utils.time import now_utc


def _capture(ws, user, ai="ok response here"):
    return CaptureRecord(session_id="s", platform=Platform.CLAUDE, user_message=user,
                         ai_response=ai, workspace_id=ws, timestamp=now_utc())


async def test_pipeline_sensitive_blocked(container, workspace):
    r = await container.pipeline.run(_capture(workspace.id, "my key sk-abc123def456ghi789jkl012mno345pqr here"))
    assert r.skipped and r.skip_reason == "sensitive_data"


async def test_pipeline_extracts_decision_and_tech(container, workspace):
    r = await container.pipeline.run(
        _capture(workspace.id, "We decided to use FastAPI and PostgreSQL for the backend.")
    )
    assert not r.skipped
    types = {c.node_type for c in r.to_commit}
    assert NodeType.TECHNICAL_FACT in types


def test_graph_commit_and_retrieve(container, workspace):
    gs = container.graph_service(workspace.id)
    gs.commit_node(workspace.id, ExtractionCandidate(node_type=NodeType.GOAL,
                   content="Ship the beta by Friday", confidence=0.9, source_pass="rule_based"))
    gs.commit_node(workspace.id, ExtractionCandidate(node_type=NodeType.DECISION,
                   content="We chose Supabase for auth", confidence=0.9, source_pass="rule_based"))
    ctx = container.retrieval_service(workspace.id).get_context(workspace.id, hint="what did we decide", platform="claude")
    assert ctx.nodes_included
    assert ctx.context_string.startswith("<context>")


def test_token_budget_respected(container, workspace):
    gs = container.graph_service(workspace.id)
    for i in range(20):
        gs.commit_node(workspace.id, ExtractionCandidate(node_type=NodeType.GOAL,
                       content=f"Goal number {i} with some descriptive content here", confidence=0.9, source_pass="rule_based"))
    ctx = container.retrieval_service(workspace.id).get_context(workspace.id, hint="goals", platform="gemini", token_budget=120)
    assert ctx.token_count <= 120


def test_structural_conflict_auto_resolves(container, workspace):
    gs = container.graph_service(workspace.id)
    cs = container.conflict_service(workspace.id)
    nr = container.node_repo(workspace.id)
    a = gs.commit_node(workspace.id, ExtractionCandidate(node_type=NodeType.TECHNICAL_FACT, content="database is PostgreSQL",
        structured_data={"entity": "database", "attribute": "technology", "value": "PostgreSQL"}, confidence=0.85, source_pass="llm"))
    b = gs.commit_node(workspace.id, ExtractionCandidate(node_type=NodeType.TECHNICAL_FACT, content="database is MongoDB",
        structured_data={"entity": "database", "attribute": "technology", "value": "MongoDB"}, confidence=0.85, source_pass="llm"))
    conflicts = cs.detect_conflicts(workspace.id, b)
    assert conflicts and conflicts[0].conflict_type.value == "direct_fact"
    ev = cs.auto_resolve(conflicts[0])
    assert ev is not None
    assert nr.get(a.id).status == NodeStatus.SUPERSEDED
    assert nr.get(b.id).status == NodeStatus.ACTIVE


def test_no_cross_workspace_contamination(container):
    a = container.workspace_service.create("WS A", "alpha")
    b = container.workspace_service.create("WS B", "beta")
    container.graph_service(a.id).commit_node(a.id, ExtractionCandidate(node_type=NodeType.GOAL,
        content="Alpha-only secret goal", confidence=0.9, source_pass="rule_based"))
    ctx_b = container.retrieval_service(b.id).get_context(b.id, hint="goal", platform="claude")
    assert all(n.node_id for n in ctx_b.nodes_included) or ctx_b.nodes_included == []
    assert "Alpha-only" not in ctx_b.context_string
