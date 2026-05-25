"""Mnemosyne engine entry point — FastAPI app, lifespan, workers (Doc 08, Doc 16)."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import MnemosyneConfig
from backend.container import ServiceContainer
from backend.errors import MnemosyneError, mnemosyne_error_handler
from backend.routes import (
    capture_routes,
    conflict_routes,
    context_routes,
    export_routes,
    extras_routes,
    graph_routes,
    health_routes,
    node_routes,
    onboarding_routes,
    pending_routes,
    settings_routes,
    websocket_routes,
    workspace_routes,
)
from backend.security.tls import generate_localhost_cert
from backend.utils.logging import setup_logging
from backend.workers.queue import DiskBackedQueue
from backend.workers.runners import (
    backup_worker,
    cleanup_worker,
    consolidation_worker,
    decay_worker,
    extraction_worker,
)

logger = logging.getLogger("mnemosyne")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MnemosyneConfig.load()
    setup_logging(config.data_dir, config.log_level)
    generate_localhost_cert(config.data_dir / "tls")

    container = ServiceContainer(config)
    queue = DiskBackedQueue(config.data_dir / "temp" / "capture_queue.jsonl", config.max_capture_queue)
    await queue.replay_unprocessed()

    app.state.container = container
    app.state.queue = queue
    app.state.start_time = time.monotonic()
    app.state.workers = [
        asyncio.create_task(extraction_worker(container, queue)),
        asyncio.create_task(decay_worker(container)),
        asyncio.create_task(consolidation_worker(container)),
        asyncio.create_task(cleanup_worker(container)),
        asyncio.create_task(backup_worker(container)),
    ]
    # Capability banner — tells the user exactly what's active (and what isn't),
    # which matters because several features degrade gracefully when optional
    # dependencies (SQLCipher, spaCy, Ollama) aren't present.
    llm_ok = await container.pipeline.llm.is_available()
    scheme = "https" if config.use_tls else "http"
    banner = (
        "\n  ┌─ Mnemosyne engine v%s ─────────────────────────\n"
        "  │  URL:         %s://%s:%s\n"
        "  │  Encryption:  %s\n"
        "  │  Embeddings:  %s\n"
        "  │  NER (spaCy): %s\n"
        "  │  LLM (Ollama):%s\n"
        "  │  Open Claude / ChatGPT / Gemini — the extension auto-pairs.\n"
        "  └────────────────────────────────────────────────\n"
    ) % (
        config.version, scheme, config.host, config.port,
        "AES-256 at rest" if container.db.encryption_active else "OFF (plaintext — install sqlcipher3)",
        "on" if container.embedding.available else "off (semantic search disabled)",
        "on" if container.pipeline.ner.available else "off (run: python -m spacy download en_core_web_sm)",
        " on" if llm_ok else " off (rules+NER only — start Ollama for deeper extraction)",
    )
    print(banner, flush=True)
    logger.info("Mnemosyne engine v%s ready on %s:%s", config.version, config.host, config.port)
    try:
        yield
    finally:
        for w in app.state.workers:
            w.cancel()
        queue.compact()
        container.shutdown()
        logger.info("Mnemosyne engine stopped")


app = FastAPI(title="Mnemosyne Engine", version="1.0.0", lifespan=lifespan)
app.add_exception_handler(MnemosyneError, mnemosyne_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

for module in (
    health_routes, capture_routes, context_routes, workspace_routes, node_routes,
    graph_routes, pending_routes, conflict_routes, settings_routes, export_routes,
    onboarding_routes, extras_routes, websocket_routes,
):
    app.include_router(module.router)


def main() -> None:
    import argparse

    import uvicorn

    config = MnemosyneConfig.load()
    parser = argparse.ArgumentParser(prog="mnemosyne-engine", description="Mnemosyne local memory engine")
    parser.add_argument("--host", default=config.host, help=f"bind host (default {config.host})")
    parser.add_argument("--port", type=int, default=config.port, help=f"bind port (default {config.port})")
    parser.add_argument("--version", action="version", version=f"mnemosyne-engine {config.version}")
    args = parser.parse_args()

    print(f"Starting Mnemosyne engine on {args.host}:{args.port} … (Ctrl+C to stop)", flush=True)
    kwargs: dict = {"host": args.host, "port": args.port}
    if config.use_tls:  # opt-in; default is loopback HTTP so the extension can connect
        kwargs["ssl_certfile"] = str(config.tls_cert_path)
        kwargs["ssl_keyfile"] = str(config.tls_key_path)
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    main()
