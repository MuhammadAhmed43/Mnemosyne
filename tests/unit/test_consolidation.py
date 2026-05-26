"""Cold-cluster summarization: old, related, rarely-used memories should collapse
into one recallable summary node, with the originals archived."""

from __future__ import annotations

from datetime import timedelta

from backend.models.enums import NodeStatus, NodeType
from backend.models.extraction import ExtractionCandidate
from backend.utils.time import now_utc


def test_cold_cluster_summarization(container, workspace):
    ws = workspace.id
    graph = container.graph_service(ws)
    repo = container.node_repo(ws)

    ids = []
    for txt in [
        "We deploy the backend on AWS ECS",
        "The infra runs on AWS with ECS and Fargate",
        "AWS is our cloud provider for the API",
        "Logs ship to AWS CloudWatch",
    ]:
        n = graph.commit_node(ws, ExtractionCandidate(
            node_type=NodeType.TECHNICAL_FACT, content=txt, confidence=0.7,
            source_pass="t", evidence="t"))
        ids.append(n.id)

    # Make them old/cold.
    old = now_utc() - timedelta(days=60)
    for nid in ids:
        repo.update_fields(nid, last_accessed=old)

    # Deterministic cluster (independent of the embedding model's exact scores).
    container.embedding.search = lambda w, q, top_k=10, exclude_node_id=None, score_threshold=0.0: [
        (i, 0.8) for i in ids if i != exclude_node_id
    ]

    cs = container.consolidation_service(ws)
    cs.ollama_url = ""  # deterministic digest path (no LLM) for a fast, stable test
    summarized = cs._summarize_cold_clusters(ws)
    assert summarized == 1

    # Only the summary remains active; the originals are archived.
    active, total = repo.list_nodes(ws, status="active")
    assert total == 1
    summary = active[0]
    assert summary.structured_data.get("kind") == "summary"
    assert summary.structured_data.get("summarized_count") == 4
    for nid in ids:
        assert repo.get(nid).status == NodeStatus.ARCHIVED
