"""Conversation thread tracking (Plan 12 §1)."""

from __future__ import annotations

import sqlite3

from backend.models.thread import ConversationThread


class ThreadRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, session_id: str, workspace_id: str, platform: str) -> ConversationThread:
        row = self.conn.execute(
            "SELECT * FROM conversation_threads WHERE session_id=?", (session_id,)
        ).fetchone()
        if row:
            return ConversationThread(**dict(row))
        thread = ConversationThread(workspace_id=workspace_id, session_id=session_id, platform=platform)
        self.conn.execute(
            "INSERT INTO conversation_threads (id, workspace_id, session_id, platform, started_at, "
            "turn_count, created_at) VALUES (?,?,?,?,?,?,?)",
            (thread.id, workspace_id, session_id, platform, thread.started_at.isoformat(),
             0, thread.created_at.isoformat()),
        )
        self.conn.commit()
        return thread

    def add_node(self, thread_id: str, node_id: str, turn_index: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO thread_nodes (thread_id, node_id, turn_index) VALUES (?,?,?)",
            (thread_id, node_id, turn_index),
        )
        self.conn.execute(
            "UPDATE conversation_threads SET turn_count = MAX(turn_count, ?) WHERE id=?",
            (turn_index + 1, thread_id),
        )
        self.conn.commit()

    def list_threads(self, workspace_id: str) -> list[ConversationThread]:
        rows = self.conn.execute(
            "SELECT * FROM conversation_threads WHERE workspace_id=? ORDER BY started_at DESC",
            (workspace_id,),
        ).fetchall()
        return [ConversationThread(**dict(r)) for r in rows]

    def get_thread_nodes(self, thread_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT tn.node_id, tn.turn_index, n.content, n.node_type "
            "FROM thread_nodes tn JOIN memory_nodes n ON n.id = tn.node_id "
            "WHERE tn.thread_id=? ORDER BY tn.turn_index",
            (thread_id,),
        ).fetchall()
        return [dict(r) for r in rows]
