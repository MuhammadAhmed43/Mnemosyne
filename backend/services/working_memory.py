"""Tier 1 working memory — in-memory, session-scoped, not persisted (Doc 04 §3).

Single home (the model/service duplication across Plan 01 + Plan 03 is resolved
here). Promotes meaningful nodes to the persistent episodic tier on session end.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from backend.models.enums import MemoryTier, NodeType
from backend.models.extraction import ExtractionCandidate
from backend.models.memory_node import MemoryNode
from backend.utils.time import now_utc

if TYPE_CHECKING:
    from backend.services.graph_service import GraphService

MAX_WORKING_MEMORY_SIZE = 50  # Doc 04 §3
PROMOTE_TYPES = {NodeType.DECISION, NodeType.GOAL, NodeType.PROBLEM}
PROMOTE_MIN_IMPORTANCE = 0.7


class WorkingMemory:
    def __init__(self, workspace_id: str, session_id: str):
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.nodes: OrderedDict[str, MemoryNode] = OrderedDict()
        self.created_at: datetime = now_utc()

    def add(self, node: MemoryNode) -> None:
        if len(self.nodes) >= MAX_WORKING_MEMORY_SIZE:
            self._evict_least_important()
        node.tier = MemoryTier.WORKING
        self.nodes[node.id] = node

    def get(self, node_id: str) -> Optional[MemoryNode]:
        return self.nodes.get(node_id)

    def all(self) -> list[MemoryNode]:
        return list(self.nodes.values())

    def _evict_least_important(self) -> None:
        if self.nodes:
            least = min(self.nodes.values(), key=lambda n: n.importance_score)
            del self.nodes[least.id]

    def flush_on_session_end(self, graph: "GraphService") -> list[MemoryNode]:
        """Promote decisions/goals/problems and high-importance nodes; discard rest."""
        promoted = []
        for node in list(self.nodes.values()):
            if node.node_type in PROMOTE_TYPES or node.importance_score > PROMOTE_MIN_IMPORTANCE:
                committed = graph.commit_node(
                    self.workspace_id,
                    ExtractionCandidate(
                        node_type=node.node_type, content=node.content,
                        structured_data=node.structured_data,
                        confidence=node.extraction_confidence,
                        source_pass="working_memory", evidence="promoted on session end",
                    ),
                    session_id=self.session_id,
                )
                promoted.append(committed)
        self.nodes.clear()
        return promoted


class WorkingMemoryManager:
    def __init__(self) -> None:
        self._sessions: dict[str, WorkingMemory] = {}

    def get_or_create(self, workspace_id: str, session_id: str) -> WorkingMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = WorkingMemory(workspace_id, session_id)
        return self._sessions[session_id]

    def end_session(self, session_id: str, graph: "GraphService") -> list[MemoryNode]:
        wm = self._sessions.pop(session_id, None)
        return wm.flush_on_session_end(graph) if wm else []
