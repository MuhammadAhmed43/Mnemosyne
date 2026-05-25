"""Data access for the global workspaces registry (Doc 07 §3.1)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from backend.models.enums import WorkspaceStatus
from backend.models.workspace import Workspace
from backend.utils.time import now_utc

_COLUMNS = [
    "id", "name", "description", "color", "icon", "status", "capture_enabled",
    "tags", "entity_count", "node_count", "memory_health_score",
    "summary_embedding_id", "summary_text", "embedding_model",
    "created_at", "updated_at", "last_active", "settings",
]

_UPDATABLE = {
    "name", "description", "color", "icon", "status", "capture_enabled", "tags",
    "entity_count", "node_count", "memory_health_score", "summary_embedding_id",
    "summary_text", "updated_at", "last_active", "settings",
}


def _ser(v: object) -> object:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if hasattr(v, "value"):
        return v.value
    return v


def row_to_workspace(row: sqlite3.Row) -> Workspace:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["settings"] = json.loads(d.get("settings") or "{}")
    d["capture_enabled"] = bool(d.get("capture_enabled"))
    return Workspace(**d)


class WorkspaceRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, ws: Workspace) -> Workspace:
        self.conn.execute(
            f"INSERT INTO workspaces ({','.join(_COLUMNS)}) "
            f"VALUES ({','.join('?' * len(_COLUMNS))})",
            [_ser(getattr(ws, c)) for c in _COLUMNS],
        )
        self.conn.commit()
        return ws

    def get(self, workspace_id: str) -> Optional[Workspace]:
        row = self.conn.execute(
            "SELECT * FROM workspaces WHERE id=?", (workspace_id,)
        ).fetchone()
        return row_to_workspace(row) if row else None

    def list(
        self, status: Optional[str] = None, sort: str = "last_active"
    ) -> list[Workspace]:
        sort_col = {"last_active": "last_active DESC", "created_at": "created_at DESC", "name": "name ASC"}.get(
            sort, "last_active DESC"
        )
        if status and status != "all":
            rows = self.conn.execute(
                f"SELECT * FROM workspaces WHERE status=? ORDER BY {sort_col}", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(f"SELECT * FROM workspaces ORDER BY {sort_col}").fetchall()
        return [row_to_workspace(r) for r in rows]

    def get_active(self) -> list[Workspace]:
        return self.list(status=WorkspaceStatus.ACTIVE.value)

    def count_active(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE status='active'"
        ).fetchone()[0]

    def update_fields(self, workspace_id: str, **fields: object) -> None:
        fields.setdefault("updated_at", now_utc())
        cols = [c for c in fields if c in _UPDATABLE]
        if not cols:
            return
        sets = ",".join(f"{c}=?" for c in cols)
        self.conn.execute(
            f"UPDATE workspaces SET {sets} WHERE id=?",
            [_ser(fields[c]) for c in cols] + [workspace_id],
        )
        self.conn.commit()

    def delete(self, workspace_id: str) -> None:
        self.conn.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
        self.conn.commit()
