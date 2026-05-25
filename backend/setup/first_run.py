"""First-run initialization (Doc 16 §2.1). Idempotent — safe to re-run."""

from __future__ import annotations

import logging

import httpx

from backend.config import MnemosyneConfig
from backend.security.tls import generate_localhost_cert

logger = logging.getLogger("mnemosyne.setup")


def is_ollama_available(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/tags", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def first_run_setup() -> MnemosyneConfig:
    """Create data dirs + token + TLS cert; report optional-component status."""
    config = MnemosyneConfig.load()  # create_default() runs on first call
    for sub in ("workspaces", "backups", "logs", "tls", "temp"):
        (config.data_dir / sub).mkdir(parents=True, exist_ok=True)
    generate_localhost_cert(config.data_dir / "tls")

    if not is_ollama_available(config.ollama_url):
        logger.warning("Ollama not found — LLM extraction disabled (rule + NER still active).")
    logger.info("First-run setup complete. Data dir: %s", config.data_dir)
    return config
