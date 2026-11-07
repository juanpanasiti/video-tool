"""Structured logging setup for video-tool.

Writes a rotating log file to the user's local data directory so post-mortem
diagnostics (e.g. moviepy/ffmpeg failures, queue worker errors) don't rely on
stderr output from a native window the user may have already closed.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def _log_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_STATE_HOME") or str(Path.home())
    return Path(base) / "video-tool" / "logs"


def configure_logging(level: int = logging.INFO) -> Path:
    """Configure the ``video_tool`` logger hierarchy with console + rotating file output.

    Returns the path to the active log file.
    """
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "video-tool.log"

    logger = logging.getLogger("video_tool")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(_LOG_FORMAT)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.WARNING)
        logger.addHandler(console_handler)

    return log_file
