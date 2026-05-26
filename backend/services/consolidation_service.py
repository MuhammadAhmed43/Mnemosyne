"""Daily consolidation: merge near-duplicates + promote tiers (Doc 10 §5)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from backend.models.enums import EdgeType, MemoryTier, NodeStatus, NodeType, Platform
from backend.models.memory_edge import MemoryEdge
from backend.models.memory_node import MemoryNode
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

# Cold-cluster summarization: compress clusters of OLD, rarely-used, related
# memories into one compact recallable "summary" node, then archive the originals
# and free their vectors. Lossy gist compression — keeps history searchable while
# the active set stays small no matter how long you use it.
COLD_DAYS = 30                  # only summarize memories untouched this long
COLD_MAX_REINFORCEMENT = 3      # ...and rarely reinforced
CLUSTER_SIM = 0.62              # neighbours within this similarity form a cluster
MIN_CLUSTER = 4                 # need at least this many to bother compressing
MAX_CLUSTERS_PER_CYCLE = 25     # bound the work per nightly run
SUMMARY_MAX_CHARS = 1500


@dataclass
class ConsolidationResult:
    workspace_id: str
    merged: int
    tiers_promoted: int
    summarized: int
    duration_ms: int


class ConsolidationService:
    def __init__(
        self,
        node_repo: NodeRepository,
        edge_repo: EdgeRepository,
        embedding: EmbeddingService,
        audit_repo: AuditRepository,
        ollama_url: str = "",
        ollama_model: str = "phi4-mini",
    ):
        self.nodes = node_repo
        self.edges = edge_repo
        self.embeddings = embedding
        self.audit = audit_repo
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model

    def run_consolidation(self, workspace_id: str) -> ConsolidationResult:
        start = time.monotonic()
        merged = self._merge_similar(workspace_id)
        promoted = self._promote_tiers(workspace_id)
        summarized = self._summarize_cold_clusters(workspace_id)
        return ConsolidationResult(
            workspace_id=workspace_id, merged=merged, tiers_promoted=promoted,
            summarized=summarized, duration_ms=int((time.monotonic() - start) * 1000),
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

    def _is_cold(self, node, cutoff) -> bool:
        return (
            not node.is_permanent
            and node.valid_until is None
            and node.last_accessed < cutoff
            and node.reinforcement_count < COLD_MAX_REINFORCEMENT
            and node.node_type != NodeType.WORKSPACE_SUMMARY
            and node.structured_data.get("kind") != "summary"  # don't re-summarize summaries
        )

    def _summarize_cold_clusters(self, workspace_id: str) -> int:
        """Cluster old/cold related memories, write one compact summary node per
        cluster, archive the originals, and delete their vectors."""
        if not self.embeddings.available:
            return 0
        cutoff = now_utc() - timedelta(days=COLD_DAYS)
        candidates = [n for n in self.nodes.get_active(workspace_id, limit=1000) if self._is_cold(n, cutoff)]
        done: set[str] = set()
        summaries = 0
        for seed in candidates:
            if seed.id in done or summaries >= MAX_CLUSTERS_PER_CYCLE:
                continue
            members = [seed]
            for mid, _score in self.embeddings.search(
                workspace_id, seed.content, top_k=15, score_threshold=CLUSTER_SIM
            ):
                if mid == seed.id or mid in done:
                    continue
                m = self.nodes.get(mid)
                if m is not None and self._is_cold(m, cutoff):
                    members.append(m)
            if len(members) < MIN_CLUSTER:
                continue
            self._write_summary(workspace_id, members)
            for m in members:
                done.add(m.id)
            summaries += 1
        return summaries

    def _llm_summarize(self, members: list) -> Optional[str]:
        """Prose summary of a cluster via the local LLM (Ollama). Returns None on
        any failure so the caller falls back to the deterministic digest. Uses a
        synchronous client — consolidation runs in a worker thread, not the loop."""
        if not self.ollama_url:
            return None
        import httpx  # noqa: PLC0415

        bullets = "\n".join(f"- [{n.node_type.value}] {n.content.strip()[:200]}" for n in members[:20])
        prompt = (
            "These are related memory items from a user's project. Summarize them into "
            "2-3 concise factual sentences capturing the key facts, decisions, and ideas "
            "so they can be recalled later. No preamble.\n\n" + bullets
        )
        try:
            with httpx.Client(timeout=45) as client:
                resp = client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self.ollama_model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2, "num_predict": 300}, "keep_alive": "5m"},
                )
                text = (resp.json().get("response") or "").strip()
                return text or None
        except Exception:  # noqa: BLE001 — LLM is best-effort; digest is the fallback
            return None

    def _write_summary(self, workspace_id: str, members: list) -> None:
        topic = " ".join(members[0].content.split()[:6])[:60]
        gist = self._llm_summarize(members) or self._digest(members)
        summary = MemoryNode(
            workspace_id=workspace_id,
            node_type=NodeType.INSIGHT,
            tier=MemoryTier.SEMANTIC,
            content=f"Summary of {len(members)} archived memories ({topic}…): {gist}"[:1800],
            structured_data={"kind": "summary", "summarized_count": len(members), "topic": topic},
            source_platform=Platform.MANUAL,
            extraction_confidence=1.0,
            extracted_at=now_utc(),
            importance_score=0.7,
            decay_rate=0.01,
        )
        self.nodes.create(summary)
        pid = self.embeddings.embed_and_store(
            workspace_id, summary.id, summary.content,
            {"node_type": summary.node_type.value, "status": "active"},
        )
        if pid:
            self.nodes.update_fields(summary.id, embedding_id=pid)
        # Archive originals, link them to the summary, and reclaim their vectors.
        for m in members:
            self.edges.create(MemoryEdge(
                workspace_id=workspace_id, source_node_id=summary.id, target_node_id=m.id,
                edge_type=EdgeType.DERIVED_FROM, weight=1.0, label="summarized cold memory",
            ))
            self.nodes.update_fields(m.id, status=NodeStatus.ARCHIVED, valid_until=now_utc())
            self.embeddings.delete(workspace_id, m.id)
        self.audit.append("cold_cluster_summarized", "node", summary.id, workspace_id,
                          {"summarized_count": len(members)})

    @staticmethod
    def _digest(members: list) -> str:
        by_type: dict[str, list[str]] = {}
        for n in members:
            by_type.setdefault(n.node_type.value, []).append(n.content.strip().replace("\n", " "))
        parts = [f"{t}: " + "; ".join(c[:140] for c in items) for t, items in by_type.items()]
        return " | ".join(parts)[:SUMMARY_MAX_CHARS]
