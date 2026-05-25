"""Data access for memory_edges (Doc 07 §2.2)."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from backend.models.enums import EdgeType
from backend.models.memory_edge import MemoryEdge
from backend.repositories._serde import ser

_COLUMNS = [
    "id", "workspace_id", "source_node_id", "target_node_id", "edge_type",
    "label", "weight", "metadata", "is_active", "valid_from", "valid_until", "created_at",
]


def row_to_edge(row: sqlite3.Row) -> MemoryEdge:
    d = dict(row)
    d["metadata"] = json.loads(d.get("metadata") or "{}")
    d["is_active"] = bool(d.get("is_active"))
    return MemoryEdge(**d)


class EdgeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, edge: MemoryEdge) -> MemoryEdge:
        self.conn.execute(
            f"INSERT INTO memory_edges ({','.join(_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(_COLUMNS))})",
            [ser(getattr(edge, c)) for c in _COLUMNS],
        )
        self.conn.commit()
        return edge

    def get_edges_for_node(self, node_id: str) -> list[MemoryEdge]:
        rows = self.conn.execute(
            "SELECT * FROM memory_edges WHERE (source_node_id=? OR target_node_id=?) "
            "AND is_active=1",
            (node_id, node_id),
        ).fetchall()
        return [row_to_edge(r) for r in rows]

    def get_all(self, workspace_id: str) -> list[MemoryEdge]:
        rows = self.conn.execute(
            "SELECT * FROM memory_edges WHERE workspace_id=? AND is_active=1", (workspace_id,)
        ).fetchall()
        return [row_to_edge(r) for r in rows]

    def find_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType
    ) -> Optional[MemoryEdge]:
        row = self.conn.execute(
            "SELECT * FROM memory_edges WHERE source_node_id=? AND target_node_id=? "
            "AND edge_type=? AND is_active=1",
            (source_id, target_id, edge_type.value),
        ).fetchone()
        return row_to_edge(row) if row else None

    def deactivate_edges_for_node(self, node_id: str) -> None:
        self.conn.execute(
            "UPDATE memory_edges SET is_active=0 WHERE source_node_id=? OR target_node_id=?",
            (node_id, node_id),
        )
        self.conn.commit()
