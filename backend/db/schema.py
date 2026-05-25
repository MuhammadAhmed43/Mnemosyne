"""SQL schema for global.db and per-workspace graph.db (Doc 07).

CHECK constraints are generated from the enums so they can never drift out of
sync (this permanently prevents the C-01 class of bug, where an enum value was
missing from the SQL CHECK and caused runtime constraint violations).
"""

from __future__ import annotations

import sqlite3
from enum import Enum

from backend.models.enums import (
    ConflictType,
    EdgeType,
    MemoryTier,
    NodeStatus,
    WorkspaceStatus,
)


def _check(col: str, enum: type[Enum]) -> str:
    vals = ", ".join(f"'{e.value}'" for e in enum)
    return f"CHECK ({col} IN ({vals}))"


# --------------------------------------------------------------------------- #
# GLOBAL DATABASE (global.db)
# --------------------------------------------------------------------------- #

def create_global_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS workspaces (
            id                   TEXT PRIMARY KEY,
            name                 TEXT NOT NULL,
            description          TEXT DEFAULT '',
            color                TEXT DEFAULT '#6366F1',
            icon                 TEXT DEFAULT '🧠',
            status               TEXT NOT NULL DEFAULT 'active',
            capture_enabled      INTEGER NOT NULL DEFAULT 1,
            tags                 TEXT DEFAULT '[]',
            entity_count         INTEGER DEFAULT 0,
            node_count           INTEGER DEFAULT 0,
            memory_health_score  REAL DEFAULT 1.0,
            summary_embedding_id TEXT,
            summary_text         TEXT,
            embedding_model      TEXT DEFAULT 'bge-m3',
            created_at           TEXT NOT NULL,
            updated_at           TEXT NOT NULL,
            last_active          TEXT NOT NULL,
            settings             TEXT DEFAULT '{{}}',
            CONSTRAINT valid_status {_check("status", WorkspaceStatus)}
        );
        CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status);
        CREATE INDEX IF NOT EXISTS idx_workspaces_last_active ON workspaces(last_active DESC);

        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id           TEXT PRIMARY KEY,
            timestamp    TEXT NOT NULL,
            action       TEXT NOT NULL,
            entity_type  TEXT NOT NULL,
            entity_id    TEXT,
            workspace_id TEXT,
            details      TEXT,
            chain_hash   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_audit_ws ON audit_log(workspace_id);

        CREATE TABLE IF NOT EXISTS platform_mappings (
            id           TEXT PRIMARY KEY,
            platform     TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            url_pattern  TEXT,
            priority     INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS onboarding_state (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS onboarding_events (
            id         TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            metadata   TEXT,
            timestamp  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_onboarding_type ON onboarding_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_onboarding_ts ON onboarding_events(timestamp DESC);

        CREATE TABLE IF NOT EXISTS network_activity (
            id          TEXT PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            destination TEXT NOT NULL,
            purpose     TEXT NOT NULL,
            is_internal INTEGER NOT NULL DEFAULT 1,
            bytes_sent  INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_network_ts ON network_activity(timestamp DESC);

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# PER-WORKSPACE DATABASE (graph.db)
# --------------------------------------------------------------------------- #

def create_workspace_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS memory_nodes (
            id                    TEXT PRIMARY KEY,
            workspace_id          TEXT NOT NULL,
            node_type             TEXT NOT NULL,
            tier                  TEXT NOT NULL DEFAULT 'episodic',
            content               TEXT NOT NULL,
            structured_data       TEXT DEFAULT '{{}}',
            source_session_id     TEXT,
            source_platform       TEXT DEFAULT 'manual',
            extraction_confidence REAL DEFAULT 1.0,
            extracted_at          TEXT,
            user_verified         INTEGER DEFAULT 0,
            importance_score      REAL DEFAULT 0.7,
            decay_rate            REAL DEFAULT 0.05,
            is_permanent          INTEGER DEFAULT 0,
            reinforcement_count   INTEGER DEFAULT 0,
            status                TEXT NOT NULL DEFAULT 'active',
            version               INTEGER DEFAULT 1,
            valid_from            TEXT NOT NULL,
            valid_until           TEXT,
            embedding_id          TEXT,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            last_accessed         TEXT NOT NULL,
            changed_by            TEXT DEFAULT 'system',
            conflicts_with        TEXT DEFAULT '[]',
            resolved_by           TEXT,
            CONSTRAINT valid_status {_check("status", NodeStatus)},
            CONSTRAINT valid_tier {_check("tier", MemoryTier)},
            CONSTRAINT valid_scores CHECK (
                importance_score BETWEEN 0 AND 1
                AND extraction_confidence BETWEEN 0 AND 1
            )
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON memory_nodes(node_type);
        CREATE INDEX IF NOT EXISTS idx_nodes_status ON memory_nodes(status);
        CREATE INDEX IF NOT EXISTS idx_nodes_tier ON memory_nodes(tier);
        CREATE INDEX IF NOT EXISTS idx_nodes_importance ON memory_nodes(importance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_nodes_valid ON memory_nodes(valid_from, valid_until);
        CREATE INDEX IF NOT EXISTS idx_nodes_session ON memory_nodes(source_session_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_created ON memory_nodes(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_nodes_accessed ON memory_nodes(last_accessed DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_nodes_fts USING fts5(
            content, structured_data,
            content=memory_nodes, content_rowid=rowid
        );

        CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON memory_nodes BEGIN
            INSERT INTO memory_nodes_fts(rowid, content, structured_data)
            VALUES (new.rowid, new.content, new.structured_data);
        END;
        CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON memory_nodes BEGIN
            INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, content, structured_data)
            VALUES ('delete', old.rowid, old.content, old.structured_data);
        END;
        CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON memory_nodes BEGIN
            INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, content, structured_data)
            VALUES ('delete', old.rowid, old.content, old.structured_data);
            INSERT INTO memory_nodes_fts(rowid, content, structured_data)
            VALUES (new.rowid, new.content, new.structured_data);
        END;

        CREATE TABLE IF NOT EXISTS node_versions (
            id              TEXT PRIMARY KEY,
            node_id         TEXT NOT NULL,
            workspace_id    TEXT NOT NULL,
            version         INTEGER NOT NULL,
            content         TEXT NOT NULL,
            structured_data TEXT DEFAULT '{{}}',
            importance_score REAL,
            valid_from      TEXT NOT NULL,
            valid_until     TEXT NOT NULL,
            change_reason   TEXT,
            changed_by      TEXT DEFAULT 'system',
            archived_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_versions_node ON node_versions(node_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_versions_workspace ON node_versions(workspace_id, node_id);

        CREATE TABLE IF NOT EXISTS memory_edges (
            id             TEXT PRIMARY KEY,
            workspace_id   TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type      TEXT NOT NULL,
            label          TEXT DEFAULT '',
            weight         REAL DEFAULT 1.0,
            metadata       TEXT DEFAULT '{{}}',
            is_active      INTEGER DEFAULT 1,
            valid_from     TEXT NOT NULL,
            valid_until    TEXT,
            created_at     TEXT NOT NULL,
            CONSTRAINT valid_edge_type {_check("edge_type", EdgeType)}
        );
        CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_node_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_node_id);
        CREATE INDEX IF NOT EXISTS idx_edges_type ON memory_edges(edge_type);
        CREATE INDEX IF NOT EXISTS idx_edges_ws_type ON memory_edges(workspace_id, edge_type);

        CREATE TABLE IF NOT EXISTS sessions (
            id                      TEXT PRIMARY KEY,
            workspace_id            TEXT NOT NULL,
            platform                TEXT NOT NULL,
            tab_url                 TEXT,
            started_at              TEXT NOT NULL,
            ended_at                TEXT,
            turn_count              INTEGER DEFAULT 0,
            capture_count           INTEGER DEFAULT 0,
            extraction_count        INTEGER DEFAULT 0,
            nodes_extracted         INTEGER DEFAULT 0,
            nodes_pending           INTEGER DEFAULT 0,
            working_memory_snapshot TEXT,
            metadata                TEXT DEFAULT '{{}}'
        );

        CREATE TABLE IF NOT EXISTS conflict_events (
            id                  TEXT PRIMARY KEY,
            workspace_id        TEXT NOT NULL,
            node_a_id           TEXT NOT NULL,
            node_b_id           TEXT NOT NULL,
            conflict_type       TEXT NOT NULL,
            similarity_score    REAL,
            contradiction_score REAL,
            status              TEXT NOT NULL DEFAULT 'pending',
            resolution_strategy TEXT,
            winning_node_id     TEXT,
            archived_node_ids   TEXT DEFAULT '[]',
            auto_resolved       INTEGER DEFAULT 0,
            resolved_by_user    TEXT,
            resolution_evidence TEXT,
            evidence            TEXT DEFAULT '',
            confidence          REAL DEFAULT 1.0,
            detected_at         TEXT NOT NULL,
            resolved_at         TEXT,
            CONSTRAINT valid_conflict_type {_check("conflict_type", ConflictType)}
        );
        CREATE INDEX IF NOT EXISTS idx_conflicts_ws ON conflict_events(workspace_id, status);

        CREATE TABLE IF NOT EXISTS pending_reviews (
            id                   TEXT PRIMARY KEY,
            workspace_id         TEXT NOT NULL,
            candidate_type       TEXT NOT NULL,
            candidate_content    TEXT NOT NULL,
            candidate_data       TEXT,
            candidate_confidence REAL,
            source_session_id    TEXT,
            source_platform      TEXT,
            source_context       TEXT,
            created_at           TEXT NOT NULL,
            expires_at           TEXT NOT NULL,
            status               TEXT NOT NULL DEFAULT 'pending',
            reviewed_at          TEXT,
            review_action        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pending_ws ON pending_reviews(workspace_id, status);
        CREATE INDEX IF NOT EXISTS idx_pending_expires ON pending_reviews(expires_at);

        -- Plan 12: conversation threads (workspace_id has NO cross-db FK; existence
        -- is enforced at the app layer — C-12).
        CREATE TABLE IF NOT EXISTS conversation_threads (
            id           TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            platform     TEXT NOT NULL,
            started_at   TEXT NOT NULL,
            ended_at     TEXT,
            turn_count   INTEGER DEFAULT 0,
            summary      TEXT,
            created_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_threads_ws ON conversation_threads(workspace_id, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_threads_session ON conversation_threads(session_id);

        CREATE TABLE IF NOT EXISTS thread_nodes (
            thread_id  TEXT NOT NULL REFERENCES conversation_threads(id),
            node_id    TEXT NOT NULL REFERENCES memory_nodes(id),
            turn_index INTEGER NOT NULL,
            PRIMARY KEY (thread_id, node_id)
        );
        CREATE INDEX IF NOT EXISTS idx_thread_nodes ON thread_nodes(thread_id);

        -- Plan 12: extraction feedback loop
        CREATE TABLE IF NOT EXISTS extraction_feedback (
            id                  TEXT PRIMARY KEY,
            node_id             TEXT,
            action              TEXT NOT NULL,
            original_type       TEXT,
            original_confidence REAL,
            corrected_type      TEXT,
            timestamp           TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_type ON extraction_feedback(original_type);
        """
    )
    conn.commit()
