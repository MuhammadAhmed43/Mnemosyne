"""Workspace merge — move one workspace's memory into another (Plan 12 §10).

Nodes/edges live in separate per-workspace graph.db files, so this is a
cross-database copy (rewrite workspace_id, re-embed under the target collection),
then archive the source workspace.
"""

from __future__ import annotations

from backend.db.manager import DatabaseManager
from backend.repositories.node_repo import NodeRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.services.embedding_service import EmbeddingService


class WorkspaceMergeService:
    def __init__(self, db: DatabaseManager, workspace_repo: WorkspaceRepository, embedding: EmbeddingService):
        self.db = db
        self.workspaces = workspace_repo
        self.embedding = embedding

    def preview(self, source_id: str, target_id: str) -> dict:
        return {
            "source_node_count": NodeRepository(self.db.get_workspace(source_id)).count(source_id),
            "target_node_count": NodeRepository(self.db.get_workspace(target_id)).count(target_id),
        }

    def execute(self, source_id: str, target_id: str) -> dict:
        src = self.db.get_workspace(source_id)
        tgt = self.db.get_workspace(target_id)

        node_rows = [dict(r) for r in src.execute("SELECT * FROM memory_nodes WHERE workspace_id=?", (source_id,))]
        edge_rows = [dict(r) for r in src.execute("SELECT * FROM memory_edges WHERE workspace_id=?", (source_id,))]

        moved = 0
        for n in node_rows:
            n["workspace_id"] = target_id
            cols = ",".join(n.keys())
            tgt.execute(f"INSERT OR IGNORE INTO memory_nodes ({cols}) VALUES ({','.join('?' * len(n))})", list(n.values()))
            # Re-embed under the target collection.
            self.embedding.embed_and_store(target_id, n["id"], n["content"], {"node_type": n["node_type"], "status": n["status"]})
            moved += 1
        for e in edge_rows:
            e["workspace_id"] = target_id
            cols = ",".join(e.keys())
            tgt.execute(f"INSERT OR IGNORE INTO memory_edges ({cols}) VALUES ({','.join('?' * len(e))})", list(e.values()))
        tgt.commit()

        self.workspaces.update_fields(source_id, status="archived")
        return {"nodes_moved": moved, "edges_moved": len(edge_rows), "source_archived": True}
