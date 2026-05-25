"""Graph diff since a timestamp — "what changed" (Plan 12 §7)."""

from __future__ import annotations

from datetime import datetime

from backend.repositories.conflict_repo import ConflictRepository
from backend.repositories.node_repo import NodeRepository


class GraphDiffService:
    def __init__(self, node_repo: NodeRepository, conflict_repo: ConflictRepository):
        self.nodes = node_repo
        self.conflicts = conflict_repo

    def get_diff(self, workspace_id: str, since: datetime) -> dict:
        def fmt(nodes):
            return [{"id": n.id, "type": n.node_type.value, "content": n.content[:80]} for n in nodes]

        added = self.nodes.get_created_since(workspace_id, since)
        updated = self.nodes.get_updated_since(workspace_id, since)
        archived = self.nodes.get_archived_since(workspace_id, since)
        new_conflicts = len(self.conflicts.get_pending(workspace_id))
        return {
            "since": since.isoformat(),
            "added": fmt(added),
            "updated": fmt(updated),
            "archived": fmt(archived),
            "new_conflicts": new_conflicts,
        }
