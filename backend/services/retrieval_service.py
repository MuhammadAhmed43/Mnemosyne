"""Multi-source context retrieval + token budgeting (Doc 10 §3, Doc 14 §4).

Consolidated from the dueling Plan 03/Plan 05 definitions into one service.
Laws enforced: goals + recent decisions always included; never return both
sides of a pending conflict; strict token budget; rank by compound retention
(importance x recency[per-node decay_rate] x reinforcement x source_weight),
never by creation date; reinforce on retrieval.
"""

from __future__ import annotations

import math
import time
from datetime import timedelta
from typing import Optional

from backend.models.context import ContextNode, ContextResult
from backend.models.enums import NodeType
from backend.models.memory_node import MemoryNode
from backend.repositories.conflict_repo import ConflictRepository
from backend.repositories.node_repo import NodeRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.intent_service import IntentService
from backend.utils.ids import generate_id
from backend.utils.time import now_utc

RECENT_DECISION_DAYS = 14
SEMANTIC_TOP_K = 10
HIGH_IMPORTANCE_MIN = 0.8
RETRIEVAL_REINFORCEMENT = 0.05  # Doc 04 §8

_PLATFORM_WRAP = {
    "claude": "<context>\n{body}\n</context>",
    "chatgpt": "[System Context]\n{body}\n[End Context]",
    "gemini": "Context from previous sessions:\n{body}",
}

_SECTION_ORDER = [
    (NodeType.GOAL, "Current Goals"),
    (NodeType.DECISION, "Recent Decisions"),
    (NodeType.USER_NOTE, "Saved Notes"),
    (NodeType.INSIGHT, "Ideas & Insights"),
    (NodeType.TECHNICAL_FACT, "Technical State"),
    (NodeType.PROBLEM, "Open Problems"),
    (NodeType.EVENT, "Recent Events"),
    (NodeType.PREFERENCE, "Working Preferences"),
    (NodeType.ENTITY, "Key People & Tools"),
    (NodeType.TASK, "Active Tasks"),
]


class RetrievalService:
    def __init__(
        self,
        node_repo: NodeRepository,
        conflict_repo: ConflictRepository,
        embedding: EmbeddingService,
        workspace_repo: WorkspaceRepository,
        intent: IntentService,
    ):
        self.nodes = node_repo
        self.conflicts = conflict_repo
        self.embeddings = embedding
        self.workspaces = workspace_repo
        self.intent = intent

    def get_context(
        self,
        workspace_id: str,
        hint: Optional[str] = None,
        platform: str = "claude",
        token_budget: int = 2000,
    ) -> ContextResult:
        start = time.monotonic()
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            return ContextResult(workspace_id=workspace_id, workspace_name="", context_string="")

        weights = self.intent.get_retrieval_weights(self.intent.classify(hint))
        total_available = self.nodes.count(workspace_id)

        # ---- gather sources ---- #
        candidates: dict[str, ContextNode] = {}

        def add(nodes: list[MemoryNode], source: str, weight: float) -> None:
            for n in nodes:
                ctx = self._score(n, source, weight)
                if n.id not in candidates or ctx.relevance_score > candidates[n.id].relevance_score:
                    candidates[n.id] = ctx

        goals = [n for n in self.nodes.get_active(workspace_id, NodeType.GOAL)
                 if n.structured_data.get("status", "ACTIVE") == "ACTIVE"]
        add(goals, "goal_priority", weights["goals"])

        cutoff = now_utc() - timedelta(days=RECENT_DECISION_DAYS)
        decisions = [n for n in self.nodes.get_active(workspace_id, NodeType.DECISION) if n.created_at >= cutoff]
        add(decisions, "recent_decision", weights["decisions"])

        problems = [n for n in self.nodes.get_active(workspace_id, NodeType.PROBLEM)
                    if n.structured_data.get("status", "OPEN") == "OPEN"]
        add(problems, "open_problem", weights["problems"])

        # Ideas/insights and user-saved notes are first-class recall material —
        # gather them so they surface even on a fresh chat with no hint yet (this
        # is the "resume working on the idea" flow). Ranking + token budget below
        # keep them from crowding out goals/decisions.
        idea_weight = weights.get("high_importance", 1.0)
        add(self.nodes.get_active(workspace_id, NodeType.INSIGHT), "insight", idea_weight)
        add(self.nodes.get_active(workspace_id, NodeType.USER_NOTE), "user_note", idea_weight)

        if hint and self.embeddings.available:
            sem_ids = [nid for nid, _ in self.embeddings.search(workspace_id, hint, top_k=SEMANTIC_TOP_K)]
            sem_nodes = [n for n in (self.nodes.get(i) for i in sem_ids) if n and n.valid_until is None]
            add(sem_nodes, "semantic", weights["semantic"])

        add(self.nodes.get_by_importance(workspace_id, HIGH_IMPORTANCE_MIN), "high_importance", weights["high_importance"])

        # Catch-all: EVERY active memory is eligible, not just goals/decisions/etc.
        # Otherwise a workspace full of facts/tasks/entities injected almost nothing
        # on a fresh chat (no hint). Ranking + the token budget below keep it ordered
        # and bounded, so this just stops type-based exclusion — it doesn't flood.
        add(self.nodes.get_active(workspace_id, limit=200), "memory", weights.get("high_importance", 1.0) * 0.5)

        # ---- filter conflicts (serve neither side) ---- #
        conflicted: set[str] = set()
        for c in self.conflicts.get_pending(workspace_id):
            conflicted.add(c.node_a_id)
            conflicted.add(c.node_b_id)
        ranked = sorted(
            (c for c in candidates.values() if c.node_id not in conflicted),
            key=lambda c: c.relevance_score, reverse=True,
        )

        # ---- token budget ---- #
        selected, used = [], 50  # reserve header
        for c in ranked:
            cost = max(1, len(c.content) // 4)
            if used + cost > token_budget:
                continue
            selected.append(c)
            used += cost

        context_string = self._build(ws.name, selected, platform)

        # ---- reinforce retrieved nodes (Doc 04 §8) ---- #
        if selected:
            self.nodes.increment_reinforcement([c.node_id for c in selected], RETRIEVAL_REINFORCEMENT)

        freshness = round(sum(c.relevance_score for c in selected) / len(selected), 3) if selected else 1.0
        return ContextResult(
            workspace_id=workspace_id,
            workspace_name=ws.name,
            context_string=context_string,
            nodes_included=selected,
            nodes_available=total_available,
            token_count=self._count(context_string),
            freshness_score=min(freshness, 1.0),
            injection_format=f"{platform}_xml" if platform == "claude" else platform,
            retrieval_ms=int((time.monotonic() - start) * 1000),
            injection_id=generate_id("inj"),
        )

    def _score(self, node: MemoryNode, source: str, weight: float) -> ContextNode:
        days = (now_utc() - node.last_accessed).total_seconds() / 86400
        recency = math.exp(-node.decay_rate * max(days, 0))  # C-05: per-node decay_rate
        reinforcement = 1.0 + 0.1 * min(node.reinforcement_count, 10)
        score = node.importance_score * recency * reinforcement * weight
        if node.user_verified:
            score *= 1.15
        return ContextNode(
            node_id=node.id, node_type=node.node_type, content=node.content,
            relevance_score=round(min(score, 2.0), 4), source=source,
        )

    def _build(self, workspace_name: str, nodes: list[ContextNode], platform: str) -> str:
        by_type: dict[NodeType, list[ContextNode]] = {}
        for n in nodes:
            by_type.setdefault(n.node_type, []).append(n)
        lines = [f"[MNEMOSYNE — Workspace: {workspace_name}]"]
        for ntype, label in _SECTION_ORDER:
            items = by_type.get(ntype)
            if items:
                lines.append(f"\n{label}:")
                lines.extend(f"• {i.content}" for i in items)
        body = "\n".join(lines)
        return _PLATFORM_WRAP.get(platform, "{body}").format(body=body)

    @staticmethod
    def _count(text: str) -> int:
        return max(1, len(text) // 4)
