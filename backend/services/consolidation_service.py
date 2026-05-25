"""Daily consolidation: merge near-duplicates + promote tiers (Doc 10 §5)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from backend.models.enums import EdgeType, MemoryTier, NodeStatus
from backend.models.memory_edge import MemoryEdge
from backend.repositories.audit_repo import AuditRepository
from backend.repositories.edge_repo import EdgeRepository
from backend.repositories.node_repo import NodeRepository
from backend.services.embedding_service import EmbeddingService
from backend.utils.time import now_utc

logger = logging.getLogger("mnemosyne.consolidation")

# Cosine threshold for near-duplicate merge (Doc 10 §5). Above paraphrase (~0.87)
# so genuinely distinct facts are not merged. Change requires re-benchmarking.
MERGE_THRESHOLD = 0.92

PROMOTE_MIN_REINFORCEMENT = 5
PROMOTE_MIN_CONFIDENCE = 0.75


@dataclass
class ConsolidationResult:
    workspace_id: str
    merged: int
    tiers_promoted: int
    duration_ms: int


class ConsolidationService:
    def __init__(
        self,
        node_repo: NodeRepository,
        edge_repo: EdgeRepository,
        embedding: EmbeddingService,
        audit_repo: AuditRepository,
    ):
        self.nodes = node_repo
        self.edges = edge_repo
        self.embeddings = embedding
        self.audit = audit_repo

    def run_consolidation(self, workspace_id: str) -> ConsolidationResult:
        start = time.monotonic()
        merged = self._merge_similar(workspace_id)
        promoted = self._promote_tiers(workspace_id)
        return ConsolidationResult(
            workspace_id=workspace_id, merged=merged, tiers_promoted=promoted,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _merge_similar(self, workspace_id: str) -> int:
        if not self.embeddings.available:
            return 0
        merged = 0
        done: set[str] = set()
        for node in self.nodes.get_active(workspace_id, limit=1000):
            if node.id in done:
                continue
            for match_id, score in self.embeddings.search(
                workspace_id, node.content, top_k=3,
                exclude_node_id=node.id, score_threshold=MERGE_THRESHOLD,
            ):
                match = self.nodes.get(match_id)
                if match is None or match.node_type != node.node_type or match.id in done:
                    continue
                winner, loser = (
                    (node, match) if node.extraction_confidence >= match.extraction_confidence
                    else (match, node)
                )
                self.nodes.update_fields(
                    loser.id, status=NodeStatus.SUPERSEDED, valid_until=now_utc(),
                    reinforcement_count=winner.reinforcement_count + loser.reinforcement_count,
                )
                self.edges.create(
                    MemoryEdge(
                        workspace_id=workspace_id, source_node_id=winner.id,
                        target_node_id=loser.id, edge_type=EdgeType.SUPERSEDES,
                        weight=round(score, 3), label="consolidated near-duplicate",
                    )
                )
                self.audit.append("node_merged", "node", loser.id, workspace_id,
                                  {"winner_id": winner.id, "similarity": round(score, 3)})
                done.add(loser.id)
                done.add(winner.id)
                merged += 1
        return merged

    def _promote_tiers(self, workspace_id: str) -> int:
        promoted = 0
        for node in self.nodes.get_active(workspace_id, limit=1000):
            if (
                node.tier == MemoryTier.EPISODIC
                and node.reinforcement_count >= PROMOTE_MIN_REINFORCEMENT
                and node.extraction_confidence >= PROMOTE_MIN_CONFIDENCE
            ):
                self.nodes.update_fields(node.id, tier=MemoryTier.SEMANTIC, decay_rate=0.01)
                promoted += 1
        return promoted
