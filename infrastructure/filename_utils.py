"""Shared filename sanitization helper for infrastructure implementations."""

from __future__ import annotations

import re

# Characters that are illegal in Windows filenames
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """Remove characters that are illegal in file names."""
    return _ILLEGAL_CHARS.sub("_", name).strip()


def escape_ffmpeg_filter_path(path: str) -> str:
    """Escape a filesystem path for use as an ffmpeg filtergraph argument (e.g. ``subtitles=``).

    Backslashes and colons (common in Windows paths like ``C:\\foo``) are
    special characters inside a filter's argument string and must be escaped,
    otherwise ffmpeg misparses the filtergraph.
    """
    return path.replace("\\", "/").replace(":", r"\:")

