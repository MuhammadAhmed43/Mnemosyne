from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from backend.models.enums import NodeType, Platform


class ContextRequest(BaseModel):
    workspace_id: Optional[str] = None  # auto-detect
    hint: Optional[str] = None  # first user message
    platform: Platform = Platform.CLAUDE
    token_budget: int = 2000
    include_types: Optional[list[NodeType]] = None


class ContextNode(BaseModel):
    node_id: str
    node_type: NodeType
    content: str
    relevance_score: float
    source: str  # "goal_priority" | "semantic" | "recent_decision" | ...


class ContextResult(BaseModel):
    workspace_id: str
    workspace_name: str
    context_string: str
    nodes_included: list[ContextNode] = Field(default_factory=list)
    nodes_available: int = 0
    token_count: int = 0
    freshness_score: float = 1.0
    injection_format: str = "claude_xml"
    retrieval_ms: int = 0
    injection_id: str = ""


class Intent(BaseModel):
    workspace_id: str
    query_vector: Optional[list[float]] = None
    hint: Optional[str] = None
    category: str = "general"
