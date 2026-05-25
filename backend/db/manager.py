"""Per-workspace + global SQLite connection management (Doc 03 §6).

The DB layer is synchronous (sqlite3 is blocking). Async service/route layers
should wrap calls with asyncio.to_thread / run_in_executor — we do NOT pretend
sqlite is async here.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from backend.config import MnemosyneConfig
from backend.db.encryption import SQLCIPHER_AVAILABLE, derive_encryption_key, open_connection
from backend.db.global_db import init_global_db
from backend.db.schema import create_workspace_schema

logger = logging.getLogger("mnemosyne.db")


class DatabaseManager:
    def __init__(self, config: MnemosyneConfig):
        self._config = config
        self._key = derive_encryption_key(
            config.data_dir,
            user_password=None,  # password mode wired later (Doc 13 §3.1)
        )
        self._connections: dict[str, sqlite3.Connection] = {}
        self._global: Optional[sqlite3.Connection] = None
        # All connections share one driver + key, so encryption state is a single
        # fact, not something to AND across opens (which mis-reported when a
        # workspace DB was opened before the global DB).
        self.encryption_active: bool = SQLCIPHER_AVAILABLE

    # --- global ---------------------------------------------------------- #
    def get_global(self) -> sqlite3.Connection:
        if self._global is None:
            path = self._config.data_dir / "global.db"
            conn, encrypted = open_connection(path, self._key)
            # Reflect the real outcome (migration can fail, or env may disable it),
            # not just whether the driver is installed.
            self.encryption_active = encrypted
            init_global_db(conn)
            self._global = conn
        return self._global

    # --- per-workspace --------------------------------------------------- #
    def get_workspace(self, workspace_id: str) -> sqlite3.Connection:
        if workspace_id not in self._connections:
            ws_dir = self._config.data_dir / "workspaces" / workspace_id
            (ws_dir / "vectors").mkdir(parents=True, exist_ok=True)
            conn, _encrypted = open_connection(ws_dir / "graph.db", self._key)
            create_workspace_schema(conn)
            self._connections[workspace_id] = conn
        return self._connections[workspace_id]

    def create_workspace_db(self, workspace_id: str) -> sqlite3.Connection:
        return self.get_workspace(workspace_id)

    def close_all(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
        if self._global is not None:
            self._global.close()
            self._global = None
