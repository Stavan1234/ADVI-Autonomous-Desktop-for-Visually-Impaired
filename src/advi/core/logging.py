from __future__ import annotations

import logging
import os
from pathlib import Path


class AdviFormatter(logging.Formatter):
    """Single foundation-level log format; user-facing output comes later."""

    def format(self, record: logging.LogRecord) -> str:
        return f"[{record.levelname}] [{record.name}] {record.getMessage()}"


def configure_logging(log_root: Path) -> None:
    log_root.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid duplicate handlers when tests or an embedding process initialize Advi twice.
    if root.handlers:
        return

    formatter = AdviFormatter()

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, os.getenv("ADVI_CONSOLE_LOG_LEVEL", "WARNING").upper(), logging.WARNING))
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_root / "advi.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    trace_logger = logging.getLogger("advi.trace")
    trace_logger.setLevel(logging.INFO)
    trace_logger.propagate = True
