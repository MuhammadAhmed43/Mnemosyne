"""Knowledge-graph write operations with temporal versioning (Doc 04, Doc 10).

commit_node: extraction candidate -> MemoryNode (importance + tier + embedding +
auto-edges + audit). update_node_content: snapshot old version to node_versions,
then update in place (history preserved, node id stable).
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.extraction.importance_scorer import compute_initial_importance
from backend.models.enums import EdgeType, MemoryTier, NodeStatus, NodeType, Platform
from backend.models.extraction import ExtractionCandidate
from backend.models.memory_edge import MemoryEdge
from backend.models.memory_node import MemoryNode, NodeVersion
from backend.repositories.audit_repo import AuditRepository
from backend.repositories.edge_repo import EdgeRepository
from backend.repositories.node_repo import NodeRepository
from backend.services.embedding_service import EmbeddingService
from backend.utils.time import now_utc

logger = logging.getLogger("mnemosyne.graph")

# Semantic dedup: collapse a candidate into an existing node when their meaning is
# nearly identical (catches rephrasings exact-match misses). Gated to longer,
# free-text types — short templated facts ("Uses Go" vs "Uses Rust") embed too
# similarly to merge safely, so those rely on exact-match only.
SEMANTIC_DUP_THRESHOLD = 0.90
SEMANTIC_DEDUP_MIN_CHARS = 25
SEMANTIC_DEDUP_TYPES = {
    NodeType.DECISION, NodeType.GOAL, NodeType.PROBLEM, NodeType.PREFERENCE,
    NodeType.INSIGHT, NodeType.USER_NOTE, NodeType.EVENT, NodeType.CONSTRAINT,
    NodeType.OPEN_QUESTION, NodeType.HYPOTHESIS,
}

# Base decay rate at creation, by type (Doc 04 §8 — status-aware refinement
# happens in decay_service at cycle time).
BASE_DECAY = {
    NodeType.DECISION: 0.02,
    NodeType.TECHNICAL_FACT: 0.01,
    NodeType.PREFERENCE: 0.005,
    NodeType.GOAL: 0.03,
    NodeType.PROBLEM: 0.04,
    NodeType.EVENT: 0.08,
    NodeType.TASK: 0.05,
    NodeType.ENTITY: 0.03,
}

TIER_BY_TYPE = {
    NodeType.GOAL: MemoryTier.SEMANTIC,
    NodeType.DECISION: MemoryTier.EPISODIC,
    NodeType.TECHNICAL_FACT: MemoryTier.SEMANTIC,
    NodeType.PREFERENCE: MemoryTier.PROCEDURAL,
    NodeType.ENTITY: MemoryTier.SEMANTIC,
    NodeType.TASK: MemoryTier.EPISODIC,
    NodeType.PROBLEM: MemoryTier.EPISODIC,
    NodeType.EVENT: MemoryTier.EPISODIC,
    NodeType.INSIGHT: MemoryTier.SEMANTIC,
    NodeType.RELATIONSHIP: MemoryTier.SEMANTIC,
    NodeType.WORKSPACE_SUMMARY: MemoryTier.SEMANTIC,
    NodeType.USER_NOTE: MemoryTier.EPISODIC,
}

# Data-tuned for bge-small-en-v1.5 cosine: related same-topic nodes score
# ~0.75-0.87, unrelated ~0.59. 0.75 captures real relations, excludes noise.
AUTO_EDGE_THRESHOLD = 0.75


class GraphService:
    def __init__(
        self,
        node_repo: NodeRepository,
        edge_repo: EdgeRepository,
        audit_repo: AuditRepository,
        embedding: EmbeddingService,
    ):
        self.nodes = node_repo
        self.edges = edge_repo
        self.audit = audit_repo
        self.embeddings = embedding

    def commit_node(
        self,
        workspace_id: str,
        candidate: ExtractionCandidate,
        session_id: Optional[str] = None,
        platform: Platform = Platform.CLAUDE,
    ) -> MemoryNode:
        # Collapse duplicates: if this exact fact already exists (active), reinforce
        # it instead of creating a near-identical node. Stops the graph filling
        # with 20x "Uses Go" when the same thing is mentioned on every turn.
        dup = self.nodes.find_active_duplicate(workspace_id, candidate.node_type, candidate.content)
        if dup is None:
            dup = self._semantic_duplicate(workspace_id, candidate)
        if dup is not None:
            self.nodes.increment_reinforcement([dup.id], 0.05)
            self.audit.append("node_deduplicated", "node", dup.id, workspace_id,
                              {"type": dup.node_type.value})
            return dup

        importance = compute_initial_importance(
            candidate.node_type, candidate.content, candidate.confidence, platform.value
        )
        node = MemoryNode(
            workspace_id=workspace_id,
            node_type=candidate.node_type,
            tier=TIER_BY_TYPE.get(candidate.node_type, MemoryTier.EPISODIC),
            content=candidate.content,
            structured_data=candidate.structured_data,
            source_session_id=session_id,
            source_platform=platform,
            extraction_confidence=candidate.confidence,
            extracted_at=now_utc(),
            importance_score=importance,
            decay_rate=BASE_DECAY.get(candidate.node_type, 0.05),
        )
        self.nodes.create(node)
        # NOTE: node_versions holds ONLY superseded versions (Doc 07 §2.3:
        # valid_until is NOT NULL there). The current/initial version lives in
        # memory_nodes; nothing is snapshotted until the first content update.

        # Embedding (semantic search + auto-edges). No-op if fastembed unavailable.
        pid = self.embeddings.embed_and_store(
            workspace_id, node.id, node.content,
            {"node_type": node.node_type.value, "status": "active"},
        )
        if pid:
            node.embedding_id = pid
            self.nodes.update_fields(node.id, embedding_id=pid)
            self._auto_edges(workspace_id, node)

        self.audit.append(
            "node_created", "node", node.id, workspace_id,
            {"type": node.node_type.value, "confidence": candidate.confidence},
        )
        return node

    def _semantic_duplicate(self, workspace_id: str, candidate: ExtractionCandidate) -> Optional[MemoryNode]:
        """Find an existing active node that means the same thing as the candidate
        (vector similarity >= threshold, same type). Returns it for reinforcement,
        or None. Skips short/templated types where embeddings over-match."""
        if not self.embeddings.available:
            return None
        if candidate.node_type not in SEMANTIC_DEDUP_TYPES:
            return None
        if len(candidate.content.strip()) < SEMANTIC_DEDUP_MIN_CHARS:
            return None
        for nid, score in self.embeddings.search(workspace_id, candidate.content, top_k=5):
            if score < SEMANTIC_DUP_THRESHOLD:
                break  # results are sorted by similarity desc — nothing else qualifies
            existing = self.nodes.get(nid)
            if (
                existing is not None
                and existing.node_type == candidate.node_type
                and existing.status == NodeStatus.ACTIVE
                and existing.valid_until is None
            ):
                return existing
        return None

    def update_node_content(
        self,
        node_id: str,
        workspace_id: str,
        new_content: str,
        structured_data: Optional[dict] = None,
        changed_by: str = "user",
        reason: Optional[str] = None,
    ) -> Optional[MemoryNode]:
        old = self.nodes.get(node_id)
        if old is None:
            return None
        # Snapshot the outgoing version BEFORE mutating (history preserved).
        self.nodes.create_version(
            NodeVersion(
                node_id=old.id, workspace_id=workspace_id, version=old.version,
                content=old.content, structured_data=old.structured_data,
                importance_score=old.importance_score, valid_from=old.valid_from,
                valid_until=now_utc(), change_reason=reason, changed_by=changed_by,
            )
        )
        self.nodes.update_fields(
            node_id,
            content=new_content,
            structured_data=structured_data if structured_data is not None else old.structured_data,
            version=old.version + 1,
            valid_from=now_utc(),
            changed_by=changed_by,
            user_verified=(changed_by == "user"),
        )
        updated = self.nodes.get(node_id)
        if updated and self.embeddings.available:
            self.embeddings.embed_and_store(
                workspace_id, node_id, new_content,
                {"node_type": updated.node_type.value, "status": updated.status.value},
            )
        self.audit.append(
            "node_updated", "node", node_id, workspace_id,
            {"version": old.version + 1, "changed_by": changed_by},
        )
        return updated

    def boost_node(self, node_id: str, workspace_id: str, importance: float, permanent: bool = False) -> None:
        self.nodes.update_fields(
            node_id, importance_score=min(1.0, importance),
            is_permanent=permanent, user_verified=True,
        )
        self.audit.append("node_boosted", "node", node_id, workspace_id,
                          {"importance": importance, "permanent": permanent})

    def archive_node(self, node_id: str, workspace_id: str, reason: str = "") -> None:
        self.nodes.update_fields(node_id, status=NodeStatus.ARCHIVED)
        self.edges.deactivate_edges_for_node(node_id)
        self.audit.append("node_archived", "node", node_id, workspace_id, {"reason": reason})

    def hard_delete_node(self, node_id: str, workspace_id: str) -> None:
        self.nodes.hard_delete(node_id)
        self.embeddings.delete(workspace_id, node_id)
        self.audit.append("node_hard_deleted", "node", node_id, workspace_id, {})

    def get_graph_data(self, workspace_id: str) -> dict:
        nodes = self.nodes.get_active(workspace_id, limit=1000)
        edges: dict[str, MemoryEdge] = {}
        for n in nodes:
            for e in self.edges.get_edges_for_node(n.id):
                edges[e.id] = e
        return {"nodes": nodes, "edges": list(edges.values())}

    def _auto_edges(self, workspace_id: str, node: MemoryNode) -> None:
        for match_id, score in self.embeddings.search(
            workspace_id, node.content, top_k=5, exclude_node_id=node.id,
            score_threshold=AUTO_EDGE_THRESHOLD,
        ):
            self.edges.create(
                MemoryEdge(
                    workspace_id=workspace_id, source_node_id=node.id,
                    target_node_id=match_id, edge_type=EdgeType.RELATES_TO,
                    weight=round(score, 3), label="auto: semantically related",
                )
            )
