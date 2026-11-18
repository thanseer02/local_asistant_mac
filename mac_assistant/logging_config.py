"""Structured rotating file logger and console logger for MacAssistant."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

LOG_DIR = Path.home() / "Library" / "Logs" / "MacAssistant"


def setup_structured_logging(debug: bool = False) -> None:
    """Configures structured rotating file logs and standard console output."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "assistant.log"

        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=2 * 1024 * 1024,  # 2MB per file
            backupCount=3,
            encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            '{"time":"%(asctime)s", "level":"%(levelname)s", "logger":"%(name)s", "msg":"%(message)s"}'
        )
        file_handler.setFormatter(file_formatter)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        stream_handler.setFormatter(stream_formatter)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG if debug else logging.INFO)

        # Clear existing handlers to prevent duplicates
        if not root.handlers:
            root.addHandler(file_handler)
            root.addHandler(stream_handler)

    except Exception as e:
        print(f"Failed setting up structured logging: {e}", file=sys.stderr)
