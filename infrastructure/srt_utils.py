"""Minimal SRT subtitle parsing/shifting helper for subclip burn-in.

Only handles the standard SRT format (index, timecode line, text, blank line).
No external dependency — this repo prefers stdlib-only parsing for a format
this simple.
"""

from __future__ import annotations

import re

_TIMECODE_LINE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _parse_timecode(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _format_timecode(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total_ms = round(seconds * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def shift_srt(content: str, offset_seconds: float, duration_seconds: float) -> str:
    """Shift all timestamps in *content* by ``-offset_seconds``, dropping entries
    entirely outside ``[0, duration_seconds]`` and clamping the rest to that range.

    Used to re-time a sidecar .srt (authored against the full source video)
    onto a cut subclip's own 0-based timeline.
    """
    blocks = re.split(r"\n\s*\n", content.strip())
    output_blocks: list[str] = []
    next_index = 1

    for block in blocks:
        lines = block.splitlines()
        timecode_line_index = next((i for i, line in enumerate(lines) if _TIMECODE_LINE.search(line)), None)
        if timecode_line_index is None:
            continue

        match = _TIMECODE_LINE.search(lines[timecode_line_index])
        assert match is not None
        start = _parse_timecode(*match.groups()[:4]) - offset_seconds
        end = _parse_timecode(*match.groups()[4:]) - offset_seconds

        if end <= 0 or start >= duration_seconds:
            continue  # entirely outside the subclip's range

        start = max(0.0, start)
        end = min(duration_seconds, end)
        if end <= start:
            continue

        text_lines = lines[timecode_line_index + 1 :]
        output_blocks.append(
            f"{next_index}\n{_format_timecode(start)} --> {_format_timecode(end)}\n"
            + "\n".join(text_lines)
        )
        next_index += 1

    return "\n\n".join(output_blocks) + ("\n" if output_blocks else "")
