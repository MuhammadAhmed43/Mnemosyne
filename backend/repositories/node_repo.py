"""Data access for memory_nodes (Doc 07, Doc 10). Synchronous SQL.

Reinforcement model (resolves Doc 04 §8 count-vs-float ambiguity): a
reinforcement event increments the integer reinforcement_count by 1 AND nudges
importance_score by the differentiated amount (retrieval 0.05, audit view 0.10,
referenced 0.20, user-confirm 0.50). The count feeds the decay bonus
1 + 0.1*min(count, 10); the importance nudge feeds retention directly.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from backend.models.enums import NodeStatus, NodeType
from backend.models.memory_node import MemoryNode, NodeVersion
from backend.utils.time import now_utc

_COLUMNS = [
    "id", "workspace_id", "node_type", "tier", "content", "structured_data",
    "source_session_id", "source_platform", "extraction_confidence", "extracted_at",
    "user_verified", "importance_score", "decay_rate", "is_permanent",
    "reinforcement_count", "status", "version", "valid_from", "valid_until",
    "embedding_id", "created_at", "updated_at", "last_accessed", "changed_by",
    "conflicts_with", "resolved_by",
]

# Columns safe to update via update_fields (whitelist guards against injection).
_UPDATABLE = {
    "tier", "content", "structured_data", "user_verified", "importance_score",
    "decay_rate", "is_permanent", "reinforcement_count", "status", "version",
    "valid_from", "valid_until", "embedding_id", "updated_at", "last_accessed",
    "changed_by", "conflicts_with", "resolved_by", "extracted_at",
}


def _dt(value: object) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else value  # type: ignore[return-value]


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def row_to_node(row: sqlite3.Row) -> MemoryNode:
    d = dict(row)
    d["structured_data"] = json.loads(d.get("structured_data") or "{}")
    d["conflicts_with"] = json.loads(d.get("conflicts_with") or "[]")
    return MemoryNode(**d)


class NodeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, node: MemoryNode) -> MemoryNode:
        values = []
        for col in _COLUMNS:
            attr = getattr(node, col)
            values.append(_serialize(attr))
        placeholders = ",".join("?" * len(_COLUMNS))
        self.conn.execute(
            f"INSERT INTO memory_nodes ({','.join(_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
        self.conn.commit()
        return node

    def get(self, node_id: str) -> Optional[MemoryNode]:
        row = self.conn.execute("SELECT * FROM memory_nodes WHERE id=?", (node_id,)).fetchone()
        return row_to_node(row) if row else None

    def get_active(
        self,
        workspace_id: str,
        node_type: Optional[NodeType] = None,
        limit: int = 100,
    ) -> list[MemoryNode]:
        q = (
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND valid_until IS NULL"
        )
        params: list[object] = [workspace_id]
        if node_type is not None:
            q += " AND node_type=?"
            params.append(node_type.value)
        q += " ORDER BY importance_score DESC LIMIT ?"
        params.append(limit)
        return [row_to_node(r) for r in self.conn.execute(q, params).fetchall()]

    def get_by_importance(self, workspace_id: str, min_score: float) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND valid_until IS NULL AND importance_score >= ? ORDER BY importance_score DESC",
            (workspace_id, min_score),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    def get_decayable(self, workspace_id: str) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND is_permanent=0",
            (workspace_id,),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    def search_fts(self, workspace_id: str, query: str, limit: int = 50) -> list[MemoryNode]:
        phrase = '"' + query.replace('"', '""') + '"'  # phrase match, escape quotes
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE rowid IN "
            "(SELECT rowid FROM memory_nodes_fts WHERE memory_nodes_fts MATCH ?) "
            "AND workspace_id=? AND status='active' LIMIT ?",
            (phrase, workspace_id, limit),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    def update_fields(self, node_id: str, **fields: object) -> None:
        cols = [c for c in fields if c in _UPDATABLE]
        if not cols:
            return
        fields.setdefault("updated_at", now_utc())
        cols = [c for c in fields if c in _UPDATABLE]
        sets = ",".join(f"{c}=?" for c in cols)
        params = [_serialize(fields[c]) for c in cols] + [node_id]
        self.conn.execute(f"UPDATE memory_nodes SET {sets} WHERE id=?", params)
        self.conn.commit()

    def increment_reinforcement(self, node_ids: list[str], importance_boost: float = 0.05) -> None:
        if not node_ids:
            return
        marks = ",".join("?" * len(node_ids))
        ts = now_utc().isoformat()
        self.conn.execute(
            f"UPDATE memory_nodes SET reinforcement_count = reinforcement_count + 1, "
            f"importance_score = MIN(1.0, importance_score + ?), last_accessed = ? "
            f"WHERE id IN ({marks})",
            [importance_boost, ts, *node_ids],
        )
        self.conn.commit()

    def update_last_accessed(self, node_ids: list[str]) -> None:
        if not node_ids:
            return
        marks = ",".join("?" * len(node_ids))
        self.conn.execute(
            f"UPDATE memory_nodes SET last_accessed=? WHERE id IN ({marks})",
            [now_utc().isoformat(), *node_ids],
        )
        self.conn.commit()

    def archive(self, node_id: str) -> None:
        self.update_fields(node_id, status=NodeStatus.ARCHIVED)

    def hard_delete(self, node_id: str) -> None:
        self.conn.execute("DELETE FROM memory_edges WHERE source_node_id=? OR target_node_id=?", (node_id, node_id))
        self.conn.execute("DELETE FROM node_versions WHERE node_id=?", (node_id,))
        self.conn.execute("DELETE FROM memory_nodes WHERE id=?", (node_id,))
        self.conn.commit()

    def count(self, workspace_id: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM memory_nodes WHERE workspace_id=? AND status='active'",
            (workspace_id,),
        ).fetchone()[0]

    def find_active_duplicate(self, workspace_id: str, node_type: NodeType, content: str) -> Optional[MemoryNode]:
        """An existing active node of the same type with case/space-insensitive
        identical content — used to collapse the same fact captured across many
        turns (e.g. 'Uses Go' extracted on every message) into one node."""
        ntype = node_type.value if hasattr(node_type, "value") else node_type
        row = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND status='active' "
            "AND node_type=? AND lower(trim(content))=lower(trim(?)) LIMIT 1",
            (workspace_id, ntype, content),
        ).fetchone()
        return row_to_node(row) if row else None

    def count_by_type(self, workspace_id: str, status: str = "active") -> dict[str, int]:
        """Per-type active node counts in one grouped query — for the dashboard
        chip row (accurate regardless of how many nodes exist, unlike a capped
        client-side tally)."""
        where, params = ["workspace_id=?"], [workspace_id]
        if status and status != "all":
            where.append("status=?")
            params.append(status)
        clause = " AND ".join(where)
        rows = self.conn.execute(
            f"SELECT node_type, COUNT(*) AS n FROM memory_nodes WHERE {clause} GROUP BY node_type",
            params,
        ).fetchall()
        return {r["node_type"]: r["n"] for r in rows}

    def count_by_type_search(self, workspace_id: str, query: str) -> dict[str, int]:
        """Per-type counts restricted to FTS matches — keeps the chip counts in
        sync with an active search."""
        phrase = '"' + query.replace('"', '""') + '"'
        rows = self.conn.execute(
            "SELECT node_type, COUNT(*) AS n FROM memory_nodes WHERE rowid IN "
            "(SELECT rowid FROM memory_nodes_fts WHERE memory_nodes_fts MATCH ?) "
            "AND workspace_id=? AND status='active' GROUP BY node_type",
            (phrase, workspace_id),
        ).fetchall()
        return {r["node_type"]: r["n"] for r in rows}

    _SORTS = {
        "importance": "importance_score DESC",
        "created_at": "created_at DESC",
        "last_accessed": "last_accessed DESC",
    }

    def list_nodes(
        self,
        workspace_id: str,
        node_type: Optional[str] = None,
        status: str = "active",
        sort: str = "importance",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryNode], int]:
        where, params = ["workspace_id=?"], [workspace_id]
        if status and status != "all":
            where.append("status=?")
            params.append(status)
        if node_type and node_type != "all":
            where.append("node_type=?")
            params.append(node_type)
        clause = " AND ".join(where)
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM memory_nodes WHERE {clause}", params
        ).fetchone()[0]
        order = self._SORTS.get(sort, "importance_score DESC")
        rows = self.conn.execute(
            f"SELECT * FROM memory_nodes WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [row_to_node(r) for r in rows], total

    # --- change queries (graph diff, Plan 12 §7) --- #
    def get_created_since(self, workspace_id: str, since: datetime) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND created_at >= ?",
            (workspace_id, since.isoformat()),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    def get_updated_since(self, workspace_id: str, since: datetime) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND updated_at >= ? "
            "AND updated_at != created_at",
            (workspace_id, since.isoformat()),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    def get_archived_since(self, workspace_id: str, since: datetime) -> list[MemoryNode]:
        rows = self.conn.execute(
            "SELECT * FROM memory_nodes WHERE workspace_id=? AND updated_at >= ? "
            "AND status IN ('archived','superseded','decayed')",
            (workspace_id, since.isoformat()),
        ).fetchall()
        return [row_to_node(r) for r in rows]

    # --- temporal versioning (node_versions) --- #
    def create_version(self, version: NodeVersion) -> None:
        self.conn.execute(
            "INSERT INTO node_versions (id, node_id, workspace_id, version, content, "
            "structured_data, importance_score, valid_from, valid_until, change_reason, "
            "changed_by, archived_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                version.id, version.node_id, version.workspace_id, version.version,
                version.content, json.dumps(version.structured_data),
                version.importance_score, _dt(version.valid_from), _dt(version.valid_until),
                version.change_reason, version.changed_by, _dt(version.archived_at),
            ),
        )
        self.conn.commit()

    def get_version_history(self, node_id: str) -> list[NodeVersion]:
        rows = self.conn.execute(
            "SELECT * FROM node_versions WHERE node_id=? ORDER BY version DESC", (node_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d.get("structured_data") or "{}")
            out.append(NodeVersion(**d))
        return out
