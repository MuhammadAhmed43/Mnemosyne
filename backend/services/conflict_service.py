"""Conflict detection + resolution (Doc 05).

Detection is deliberately FALSE-POSITIVE-CONSERVATIVE (Doc 14, Doc 05 §8 target
<15% FP). We detect the cases that are reliably contradictions:
  - Structural (Method B): same entity+attribute slot, different value. Only
    fires on explicitly-structured facts (LLM/user), never generic rule facts
    (entity='tech', no attribute) which would over-flag polyglot stacks.
  - Goal-state (Method C): an EVENT that completes an active GOAL.
  - Circular relationship (Type 5): A depends_on B AND B depends_on A.
General semantic (NLI) contradiction detection is left as a hook for when the
local LLM is available — naive embedding-similarity flagging produces too many
false positives (e.g. "uses Python" vs "uses TypeScript" are not a conflict).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from backend.models.conflict import ConflictCandidate, ResolutionEvent
from backend.models.enums import (
    ConflictStrategy,
    ConflictType,
    EdgeType,
    NodeStatus,
    ResolutionStatus,
)
from backend.models.memory_edge import MemoryEdge
from backend.models.memory_node import MemoryNode
from backend.repositories.conflict_repo import ConflictRepository
from backend.repositories.edge_repo import EdgeRepository
from backend.repositories.node_repo import NodeRepository
from backend.services.embedding_service import EmbeddingService
from backend.utils.time import now_utc

logger = logging.getLogger("mnemosyne.conflict")

GOAL_COMPLETION_PHRASES = (
    "completed", "finished", "shipped", "launched", "deployed",
    "done", "delivered", "submitted", "wrapped up", "went live",
)
GOAL_STATE_SIM_THRESHOLD = 0.75

# --- "change of plans" tech switch detection -------------------------------- #
# A switch within the SAME category (e.g. one language -> another) for the same
# project is a real contradiction the user expects to see. Mutually-exclusive
# choices live in the same category; cross-category combos (Python + React) are
# legitimate polyglot stacks and must NOT flag.
TECH_CATEGORY: dict[str, str] = {
    # languages
    "python": "language", "typescript": "language", "javascript": "language",
    "rust": "language", "go": "language", "golang": "language", "java": "language",
    "kotlin": "language", "swift": "language", "ruby": "language", "c#": "language", "php": "language",
    # databases
    "postgresql": "database", "postgres": "database", "mysql": "database", "mongodb": "database",
    "sqlite": "database", "redis": "database", "cassandra": "database", "dynamodb": "database",
    "supabase": "database", "firebase": "database",
    # frontend frameworks
    "react": "frontend", "vue": "frontend", "angular": "frontend", "svelte": "frontend",
    "next.js": "frontend", "nextjs": "frontend", "nuxt": "frontend", "remix": "frontend",
    # backend frameworks
    "fastapi": "backend", "django": "backend", "flask": "backend", "express": "backend",
    "spring": "backend", "rails": "backend", "laravel": "backend",
    # cloud / hosting (usually a single primary target)
    "aws": "cloud", "gcp": "cloud", "azure": "cloud", "vercel": "cloud",
    "railway": "cloud", "render": "cloud", "fly.io": "cloud", "netlify": "cloud",
}
TECH_ALIASES = {"golang": "go", "postgres": "postgresql", "nextjs": "next.js"}

# Explicit "I'm changing my mind" cues — the signal that distinguishes a switch
# from a first-time choice or a polyglot addition.
SWITCH_CUE = re.compile(
    r"\b(change of plans?|changed my mind|on second thought|actually,?|"
    r"instead(?:\s+of)?|rather than|scrap(?:\s+that)?|forget|no longer|"
    r"switch(?:ing|ed)?\s+to|migrat(?:e|ing|ed)\s+to|port(?:ing|ed)?\s+to|"
    r"rewrit(?:e|ing)\s+in|moving\s+to|let'?s\s+(?:use|go\s+with)\s+\w+\s+instead)\b",
    re.IGNORECASE,
)


class ConflictService:
    def __init__(
        self,
        node_repo: NodeRepository,
        edge_repo: EdgeRepository,
        conflict_repo: ConflictRepository,
        embedding: EmbeddingService,
    ):
        self.nodes = node_repo
        self.edges = edge_repo
        self.conflicts = conflict_repo
        self.embeddings = embedding

    # ---- detection ----------------------------------------------------- #
    def detect_conflicts(self, workspace_id: str, new_node: MemoryNode) -> list[ConflictCandidate]:
        found = self._detect_structural(workspace_id, new_node)
        found += self._detect_goal_state(workspace_id, new_node)
        found += self._detect_choice_change(workspace_id, new_node)
        # dedup by node pair
        seen, unique = set(), []
        for c in found:
            key = frozenset((c.node_a_id, c.node_b_id))
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def _detect_structural(self, workspace_id: str, new_node: MemoryNode) -> list[ConflictCandidate]:
        sd = new_node.structured_data
        entity, attribute, value = sd.get("entity"), sd.get("attribute"), sd.get("value")
        if not (entity and attribute and value):
            return []  # generic rule facts (no attribute) skip -> avoids FP
        rows = self.nodes.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND valid_until IS NULL AND id != ? "
            "AND json_extract(structured_data,'$.entity')=? "
            "AND json_extract(structured_data,'$.attribute')=? "
            "AND json_extract(structured_data,'$.value') != ?",
            (workspace_id, new_node.id, entity, attribute, value),
        ).fetchall()
        out = []
        for r in rows:
            other = self.nodes.get(r["id"])
            if other is None:
                continue
            out.append(
                ConflictCandidate(
                    workspace_id=workspace_id,
                    node_a_id=other.id,
                    node_b_id=new_node.id,
                    conflict_type=ConflictType.DIRECT_FACT,
                    contradiction_score=0.95,
                    suggested_strategy=ConflictStrategy.TEMPORAL,
                    auto_resolvable=not (other.user_verified or new_node.user_verified),
                )
            )
        return out

    def _detect_goal_state(self, workspace_id: str, new_node: MemoryNode) -> list[ConflictCandidate]:
        from backend.models.enums import NodeType  # local to avoid cycle at top

        if new_node.node_type != NodeType.EVENT:
            return []
        if not any(p in new_node.content.lower() for p in GOAL_COMPLETION_PHRASES):
            return []
        if not self.embeddings.available:
            return []
        out = []
        for node_id, score in self.embeddings.search(
            workspace_id, new_node.content, top_k=10,
            exclude_node_id=new_node.id, score_threshold=GOAL_STATE_SIM_THRESHOLD,
        ):
            goal = self.nodes.get(node_id)
            if (
                goal
                and goal.node_type == NodeType.GOAL
                and goal.status == NodeStatus.ACTIVE
                and goal.structured_data.get("status", "ACTIVE") == "ACTIVE"
            ):
                out.append(
                    ConflictCandidate(
                        workspace_id=workspace_id,
                        node_a_id=goal.id,
                        node_b_id=new_node.id,
                        conflict_type=ConflictType.GOAL_STATE,
                        similarity_score=score,
                        contradiction_score=score,
                        suggested_strategy=ConflictStrategy.TEMPORAL,
                        auto_resolvable=not goal.user_verified,
                    )
                )
        return out

    @staticmethod
    def _techs_in(text: str) -> dict[str, str]:
        """Map category -> canonical tech mentioned in `text` (word-boundary, case-insensitive)."""
        low = (text or "").lower()
        out: dict[str, str] = {}
        for tech, cat in TECH_CATEGORY.items():
            # word-ish boundary; escape dots in names like "next.js"/"fly.io"
            if re.search(rf"(?<![\w]){re.escape(tech)}(?![\w])", low):
                out[cat] = TECH_ALIASES.get(tech, tech)
        return out

    def _detect_choice_change(self, workspace_id: str, new_node: MemoryNode) -> list[ConflictCandidate]:
        """Type VERSION_FORK: the user switches a tech/tool choice for the project
        (e.g. "change of plans, use Go" after "build it in Python"). Gated on an
        explicit switch cue so polyglot additions (Python + React) never flag.
        Left for the user to resolve (auto_resolvable=False) so it stays visible."""
        from backend.models.enums import NodeType  # local to avoid cycle at top

        if new_node.node_type not in (NodeType.DECISION, NodeType.TECHNICAL_FACT):
            return []
        if not SWITCH_CUE.search(new_node.content):
            return []
        new_techs = self._techs_in(new_node.content)
        if not new_techs:
            return []

        rows = self.nodes.conn.execute(
            "SELECT id FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND valid_until IS NULL AND id != ? "
            "AND node_type IN ('decision','technical_fact')",
            (workspace_id, new_node.id),
        ).fetchall()
        out: list[ConflictCandidate] = []
        seen: set[str] = set()
        for r in rows:
            prior = self.nodes.get(r["id"])
            if prior is None or prior.id in seen:
                continue
            prior_techs = self._techs_in(prior.content)
            # Same category, different chosen tech => a real switch/contradiction.
            if any(cat in prior_techs and prior_techs[cat] != tech for cat, tech in new_techs.items()):
                seen.add(prior.id)
                out.append(
                    ConflictCandidate(
                        workspace_id=workspace_id,
                        node_a_id=prior.id,
                        node_b_id=new_node.id,
                        conflict_type=ConflictType.VERSION_FORK,
                        contradiction_score=0.85,
                        suggested_strategy=ConflictStrategy.TEMPORAL,
                        auto_resolvable=False,  # surface it; the user decides which choice stands
                    )
                )
        return out

    def detect_relationship_conflict(
        self, workspace_id: str, new_edge: MemoryEdge
    ) -> Optional[ConflictCandidate]:
        """Type 5: circular dependency. Never auto-resolved (Doc 05 §4)."""
        if new_edge.edge_type not in (EdgeType.DEPENDS_ON, EdgeType.BLOCKS, EdgeType.BLOCKED_BY):
            return None
        inverse = self.edges.find_edge(
            new_edge.target_node_id, new_edge.source_node_id, new_edge.edge_type
        )
        if inverse is None:
            return None
        return ConflictCandidate(
            workspace_id=workspace_id,
            node_a_id=new_edge.source_node_id,
            node_b_id=new_edge.target_node_id,
            conflict_type=ConflictType.LOGICAL_ERROR,
            contradiction_score=1.0,
            suggested_strategy=ConflictStrategy.LOGICAL_FLAG,
            auto_resolvable=False,
        )

    # ---- resolution ---------------------------------------------------- #
    def auto_resolve(self, conflict: ConflictCandidate) -> Optional[ResolutionEvent]:
        if not conflict.auto_resolvable:
            return None
        a, b = self.nodes.get(conflict.node_a_id), self.nodes.get(conflict.node_b_id)
        if a is None or b is None:
            return None

        if conflict.conflict_type == ConflictType.GOAL_STATE:
            # a = goal, b = completion event. Mark goal COMPLETED, link, keep both.
            sd = {**a.structured_data, "status": "COMPLETED", "completed_at": now_utc().isoformat()}
            self.nodes.update_fields(a.id, structured_data=sd)
            self.edges.create(
                MemoryEdge(
                    workspace_id=conflict.workspace_id, source_node_id=b.id,
                    target_node_id=a.id, edge_type=EdgeType.RESOLVED_BY,
                    label="goal completed by event",
                )
            )
            return self._event(conflict, ConflictStrategy.TEMPORAL, winning=a.id, archived=[],
                               evidence="goal marked completed by event")

        # DIRECT_FACT etc: pick winner, supersede loser
        if conflict.suggested_strategy == ConflictStrategy.CONFIDENCE_WEIGHTED:
            winner, loser = (a, b) if a.extraction_confidence >= b.extraction_confidence else (b, a)
        else:  # TEMPORAL
            winner, loser = (b, a) if b.created_at >= a.created_at else (a, b)

        self.nodes.update_fields(loser.id, status=NodeStatus.SUPERSEDED, valid_until=now_utc())
        self.edges.create(
            MemoryEdge(
                workspace_id=conflict.workspace_id, source_node_id=winner.id,
                target_node_id=loser.id, edge_type=EdgeType.SUPERSEDES,
                label=f"supersedes: {loser.content[:40]}",
            )
        )
        return self._event(conflict, conflict.suggested_strategy, winning=winner.id,
                           archived=[loser.id], evidence="newer/higher-confidence wins")

    def user_resolve(
        self,
        conflict: ConflictCandidate,
        winning_node_id: Optional[str] = None,
        custom_resolution: Optional[str] = None,
        reason: str = "",
    ) -> ResolutionEvent:
        archived = []
        if winning_node_id:
            loser_id = conflict.node_b_id if winning_node_id == conflict.node_a_id else conflict.node_a_id
            self.nodes.update_fields(loser_id, status=NodeStatus.SUPERSEDED, valid_until=now_utc())
            archived = [loser_id]
        return ResolutionEvent(
            workspace_id=conflict.workspace_id, conflict_id=conflict.id,
            conflict_type=conflict.conflict_type, strategy_used=ConflictStrategy.USER_REVIEW,
            status=ResolutionStatus.USER_RESOLVED, winning_node_id=winning_node_id,
            archived_node_ids=archived, custom_resolution=custom_resolution,
            evidence=reason, resolved_by="user",
        )

    def _event(self, conflict, strategy, winning, archived, evidence) -> ResolutionEvent:
        return ResolutionEvent(
            workspace_id=conflict.workspace_id, conflict_id=conflict.id,
            conflict_type=conflict.conflict_type, strategy_used=strategy,
            status=ResolutionStatus.AUTO_RESOLVED, winning_node_id=winning,
            archived_node_ids=archived, evidence=evidence, resolved_by="system",
        )
