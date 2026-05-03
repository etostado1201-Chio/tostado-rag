"""
logging_config.py
-----------------
Structured JSON logging for the Flask backend.

Why JSON instead of plain text? It's the least amount of work that
makes the logs ingestible by any aggregator (CloudWatch, Datadog,
Loki, Splunk) without changes — useful even for a small project.

Usage:
    from .logging_config import configure_logging
    configure_logging()
    log = logging.getLogger("tostado.app")
    log.info("ready", extra={"port": 5000})
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render every log record as a single-line JSON object."""

    # Standard LogRecord attributes we don't want to bury in `fields`.
    _RESERVED = frozenset({
        "args", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message",
        "msg", "name", "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":     time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        # Anything passed via `extra=` lives directly on the record.
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Idempotent — safe to call from create_app() or scripts."""
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down noisy third-party libraries by default.
    for noisy in ("urllib3", "httpx", "sentence_transformers", "transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
