"""Unit tests for infrastructure/srt_utils.py::shift_srt."""

from __future__ import annotations

from infrastructure.srt_utils import shift_srt

_SAMPLE = """1
00:00:01,000 --> 00:00:02,000
Hello

2
00:00:03,000 --> 00:00:04,500
World

3
00:00:20,000 --> 00:00:21,000
Too late
"""


def test_shift_srt_offsets_timestamps_and_renumbers() -> None:
    result = shift_srt(_SAMPLE, offset_seconds=1.0, duration_seconds=10.0)

    assert "1\n00:00:00,000 --> 00:00:01,000\nHello" in result
    assert "2\n00:00:02,000 --> 00:00:03,500\nWorld" in result


def test_shift_srt_drops_entries_outside_duration() -> None:
    result = shift_srt(_SAMPLE, offset_seconds=1.0, duration_seconds=10.0)

    assert "Too late" not in result


def test_shift_srt_clamps_entries_crossing_duration_boundary() -> None:
    result = shift_srt(_SAMPLE, offset_seconds=0.0, duration_seconds=3.5)

    # "World" (3.0-4.5) should be clamped to end at 3.5
    assert "00:00:03,000 --> 00:00:03,500\nWorld" in result


def test_shift_srt_empty_input_returns_empty_string() -> None:
    assert shift_srt("", offset_seconds=0.0, duration_seconds=10.0) == ""


def test_shift_srt_all_entries_outside_range_returns_empty() -> None:
    result = shift_srt(_SAMPLE, offset_seconds=100.0, duration_seconds=10.0)
    assert result == ""
