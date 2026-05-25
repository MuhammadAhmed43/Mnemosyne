"""Markdown snapshot export of a workspace (Plan 12 §3). Per-workspace data."""

from __future__ import annotations

from backend.models.enums import NodeType
from backend.repositories.node_repo import NodeRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.utils.time import now_utc

_ORDER = [
    (NodeType.GOAL, "Active Goals"),
    (NodeType.DECISION, "Decisions"),
    (NodeType.PROBLEM, "Open Problems"),
    (NodeType.TECHNICAL_FACT, "Technical State"),
    (NodeType.EVENT, "Events"),
    (NodeType.ENTITY, "Key People & Tools"),
    (NodeType.PREFERENCE, "Preferences"),
    (NodeType.TASK, "Tasks"),
]


class SnapshotService:
    def __init__(self, node_repo: NodeRepository, workspace_repo: WorkspaceRepository):
        self.nodes = node_repo
        self.workspaces = workspace_repo

    def export_markdown(self, workspace_id: str) -> str:
        ws = self.workspaces.get(workspace_id)
        nodes = self.nodes.get_active(workspace_id, limit=1000)
        grouped: dict[NodeType, list] = {}
        for n in nodes:
            grouped.setdefault(n.node_type, []).append(n)

        lines = [
            f"# Workspace: {ws.name if ws else workspace_id}",
            f"## Exported: {now_utc().strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total memories:** {len(nodes)}",
            "",
        ]
        for ntype, label in _ORDER:
            items = grouped.get(ntype)
            if not items:
                continue
            lines.append(f"### {label} ({len(items)})")
            for n in sorted(items, key=lambda x: -x.importance_score):
                extra = ""
                if ntype == NodeType.DECISION and n.structured_data.get("rationale"):
                    extra = f" — {n.structured_data['rationale']}"
                elif ntype == NodeType.GOAL:
                    extra = f" [{n.structured_data.get('status', 'ACTIVE')}]"
                lines.append(f"- {n.content}{extra}")
            lines.append("")
        return "\n".join(lines)
