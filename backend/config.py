"""Engine configuration + platform-aware data directory (Doc 11, Doc 16 §2)."""

from __future__ import annotations

import json
import os
import platform
import secrets
from pathlib import Path

from pydantic import BaseModel


def get_data_dir() -> Path:
    """Where Mnemosyne stores everything. `MNEMOSYNE_DATA_DIR` overrides on every
    platform (used for tests, Docker, and custom locations); otherwise it's
    %APPDATA%\\Mnemosyne on Windows and ~/.mnemosyne on macOS/Linux."""
    override = os.environ.get("MNEMOSYNE_DATA_DIR")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "Mnemosyne"
    return Path.home() / ".mnemosyne"


# Embeddings run in-process via fastembed (ONNX, no daemon). The default
# bge-small-en-v1.5 is 384-dim, which matches Doc 04's original spec and
# resolves the dimension inconsistency. Larger models available if needed.
EMBEDDING_DIMS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-m3": 1024,
}


class MnemosyneConfig(BaseModel):
    version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 7432

    # Filled on first run
    auth_token: str = ""

    # Ollama (LLM extraction + embeddings)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "phi4-mini"  # LLM extraction pass only
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # fastembed, in-process
    embedding_dim: int = 384

    # Behaviour
    log_level: str = "INFO"
    max_capture_queue: int = 100
    backup_retention_days: int = 7
    decay_interval_hours: int = 6
    consolidation_hour: int = 3  # 3am local
    max_active_workspaces: int = 50  # Doc 02 enforced limit (Doc 03's 100 = design ceiling)
    # Token pairing: /pair serves the auth token to the extension only during a
    # short window after startup (the sandboxed extension can't read config.json).
    pairing_window_seconds: int = 600

    # Encryption: machine-key by default; password mode opt-in (Doc 13 §3.1)
    use_password_encryption: bool = False
    # Transport: loopback HTTP by default. A self-signed cert on localhost can't be
    # trusted by the extension's fetch, so HTTPS would break the connection. HTTP on
    # 127.0.0.1 + bearer token is the right call for a single-user local daemon.
    use_tls: bool = False

    @property
    def data_dir(self) -> Path:
        return get_data_dir()

    @property
    def tls_cert_path(self) -> Path:
        return self.data_dir / "tls" / "cert.pem"

    @property
    def tls_key_path(self) -> Path:
        return self.data_dir / "tls" / "key.pem"

    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.json"

    @classmethod
    def load(cls) -> "MnemosyneConfig":
        path = get_data_dir() / "config.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        return cls.create_default()

    @classmethod
    def create_default(cls) -> "MnemosyneConfig":
        """First run: create dirs, generate auth token + salt, persist config."""
        data_dir = get_data_dir()
        for subdir in ("workspaces", "backups", "logs", "tls", "temp"):
            (data_dir / subdir).mkdir(parents=True, exist_ok=True)

        salt_path = data_dir / "salt"
        if not salt_path.exists():
            salt_path.write_bytes(os.urandom(32))

        cfg = cls(auth_token=secrets.token_urlsafe(32))
        cfg.embedding_dim = EMBEDDING_DIMS.get(cfg.embedding_model, 384)
        cfg.save()
        return cfg

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
