"""Natural-language graph query (Plan 12 §11).

Works without the LLM: embeds the question for semantic search and runs FTS over
its keywords, merging results. If Ollama is available it could additionally parse
the question into typed filters (future enhancement) — but the semantic+FTS path
is the always-available baseline.
"""

from __future__ import annotations

import re

from backend.models.memory_node import MemoryNode
from backend.repositories.node_repo import NodeRepository
from backend.services.embedding_service import EmbeddingService

_STOP = {"what", "which", "did", "do", "i", "we", "the", "a", "an", "about", "on", "for", "of", "is", "are", "make", "made", "my", "our"}


class NaturalLanguageQueryService:
    def __init__(self, node_repo: NodeRepository, embedding: EmbeddingService):
        self.nodes = node_repo
        self.embedding = embedding

    def query(self, workspace_id: str, question: str, top_k: int = 15) -> list[MemoryNode]:
        results: dict[str, MemoryNode] = {}

        # Semantic
        if self.embedding.available:
            for nid, _score in self.embedding.search(workspace_id, question, top_k=top_k):
                node = self.nodes.get(nid)
                if node and node.valid_until is None:
                    results[nid] = node

        # Keyword FTS
        keywords = [w for w in re.findall(r"[A-Za-z0-9]+", question.lower()) if w not in _STOP and len(w) > 2]
        for kw in keywords[:5]:
            for node in self.nodes.search_fts(workspace_id, kw, limit=top_k):
                results[node.id] = node

        return list(results.values())[:top_k]
