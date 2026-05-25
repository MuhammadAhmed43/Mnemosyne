"""Weekly integrity check: PRAGMA integrity_check + orphaned-edge detection (Doc 07 §6)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class IntegrityReport:
    sqlite_ok: bool
    orphaned_edge_count: int
    orphaned_edge_ids: list[str] = field(default_factory=list)


def check_integrity(conn: sqlite3.Connection) -> IntegrityReport:
    results = conn.execute("PRAGMA integrity_check").fetchall()
    ok = bool(results) and results[0][0] == "ok"
    orphaned = conn.execute(
        """
        SELECT e.id FROM memory_edges e
        LEFT JOIN memory_nodes n ON n.id = e.source_node_id
        WHERE n.id IS NULL
        UNION
        SELECT e.id FROM memory_edges e
        LEFT JOIN memory_nodes n ON n.id = e.target_node_id
        WHERE n.id IS NULL
        """
    ).fetchall()
    ids = [r[0] for r in orphaned]
    return IntegrityReport(sqlite_ok=ok, orphaned_edge_count=len(ids), orphaned_edge_ids=ids)
