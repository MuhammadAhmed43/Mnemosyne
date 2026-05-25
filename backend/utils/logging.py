"""Structured JSON logging, daily rotation (Doc 16 §5.1, C-10).

NEVER logs message/node content — only metadata (Doc 14 §1).
"""

from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from backend.utils.time import now_utc


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": now_utc().isoformat() + "Z",
                "level": record.levelname,
                "component": record.name.split(".")[-1],
                "event": record.getMessage(),
            }
        )


def setup_logging(data_dir: Path, level: str = "INFO") -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    def handler(filename: str, min_level: int = logging.NOTSET) -> TimedRotatingFileHandler:
        h = TimedRotatingFileHandler(
            log_dir / filename, when="midnight", interval=1, backupCount=7, encoding="utf-8", utc=True
        )
        h.setFormatter(JsonFormatter())
        if min_level:
            h.setLevel(min_level)
        return h

    root = logging.getLogger("mnemosyne")
    root.setLevel(getattr(logging, level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler("engine.log"))
    root.addHandler(handler("engine_err.log", logging.ERROR))
    logging.getLogger("mnemosyne.extraction").addHandler(handler("extraction.log"))

    # Human-readable console handler so someone running `mnemosyne-engine` sees
    # what's happening (files stay JSON for tooling).
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(console)
