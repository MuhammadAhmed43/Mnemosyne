"""Memory decay: retention scoring + 4-tier decay actions (Doc 04 §8, Doc 10 §4)."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from backend.models.enums import MemoryTier, NodeStatus, NodeType
from backend.models.memory_node import MemoryNode
from backend.repositories.audit_repo import AuditRepository
from backend.repositories.node_repo import NodeRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.utils.time import now_utc

logger = logging.getLogger("mnemosyne.decay")


@dataclass
class DecayCycleResult:
    workspace_id: str
    active: int
    demoted: int
    archived: int
    pruned: int
    duration_ms: int


# Status-aware decay rates (Doc 04 §8). Key: (node_type, status) or (node_type, None).
DECAY_RATES = {
    (NodeType.TASK, "TODO"): 0.05,
    (NodeType.TASK, "IN_PROGRESS"): 0.05,
    (NodeType.TASK, "DONE"): 0.15,
    (NodeType.TASK, "BLOCKED"): 0.04,
    (NodeType.GOAL, "ACTIVE"): 0.03,
    (NodeType.GOAL, "COMPLETED"): 0.20,
    (NodeType.GOAL, "ABANDONED"): 0.20,
    (NodeType.PROBLEM, "OPEN"): 0.04,
    (NodeType.PROBLEM, "RESOLVED"): 0.12,
    (NodeType.DECISION, None): 0.02,
    (NodeType.TECHNICAL_FACT, None): 0.01,
    (NodeType.EVENT, None): 0.08,
    (NodeType.PREFERENCE, None): 0.005,
    (NodeType.ENTITY, None): 0.03,
    (NodeType.INSIGHT, None): 0.04,
}
TIER_FALLBACK = {
    MemoryTier.WORKING: 0.50,
    MemoryTier.EPISODIC: 0.05,
    MemoryTier.SEMANTIC: 0.01,
    MemoryTier.PROCEDURAL: 0.005,
}
WS_RELEVANCE = {"active": 1.0, "paused": 0.5, "archived": 0.2}


class DecayService:
    def __init__(self, node_repo: NodeRepository, workspace_repo: WorkspaceRepository, audit_repo: AuditRepository):
        self.nodes = node_repo
        self.workspaces = workspace_repo
        self.audit = audit_repo

    def effective_decay_rate(self, node: MemoryNode) -> float:
        status = node.structured_data.get("status")
        return (
            DECAY_RATES.get((node.node_type, status))
            or DECAY_RATES.get((node.node_type, None))
            or TIER_FALLBACK.get(node.tier, 0.05)
        )

    def compute_retention(self, node: MemoryNode, workspace_status: str = "active") -> float:
        if node.is_permanent:
            return 1.0
        days = (now_utc() - node.last_accessed).total_seconds() / 86400
        recency = math.exp(-self.effective_decay_rate(node) * max(days, 0))
        reinforcement = 1.0 + 0.1 * min(node.reinforcement_count, 10)
        relevance = WS_RELEVANCE.get(workspace_status, 1.0)
        return min(node.importance_score * recency * reinforcement * relevance, 1.0)

    def run_decay_cycle(self, workspace_id: str) -> DecayCycleResult:
        start = time.monotonic()
        ws = self.workspaces.get(workspace_id)
        ws_status = ws.status.value if ws else "active"
        stats = {"active": 0, "demoted": 0, "archived": 0, "pruned": 0}

        for node in self.nodes.get_decayable(workspace_id):
            retention = self.compute_retention(node, ws_status)
            if retention < 0.2:
                self.nodes.update_fields(node.id, status=NodeStatus.DECAYED)
                self.audit.append("node_pruned", "node", node.id, workspace_id, {"retention": round(retention, 3)})
                stats["pruned"] += 1
            elif retention < 0.4:
                self.nodes.update_fields(node.id, status=NodeStatus.ARCHIVED)
                self.audit.append("node_decayed", "node", node.id, workspace_id, {"retention": round(retention, 3)})
                stats["archived"] += 1
            elif retention < 0.6:
                self.nodes.update_fields(node.id, importance_score=max(0.1, retention * node.importance_score))
                stats["demoted"] += 1
            else:
                stats["active"] += 1

        return DecayCycleResult(
            workspace_id=workspace_id, duration_ms=int((time.monotonic() - start) * 1000), **stats
        )
