"""Integration tests for infrastructure/moviepy_concatenator.py (real ffmpeg encode/decode)."""

from __future__ import annotations

from pathlib import Path

from domain.models import ClipInterval, ClipResult
from infrastructure.moviepy_clipper import MoviePyClipper
from infrastructure.moviepy_concatenator import MoviePyConcatenator
from infrastructure.video_repository import VideoRepository


def _make_clip(sample_video: Path, tmp_path: Path, title: str) -> ClipResult:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="1", title=title)
    target = tmp_path / "parts"
    target.mkdir(exist_ok=True)
    return MoviePyClipper().cut(video=video, interval=interval, target=target)


def test_concatenate_joins_two_clips_into_one_file(sample_video: Path, tmp_path: Path) -> None:
    clip1 = _make_clip(sample_video, tmp_path, "part1")
    clip2 = _make_clip(sample_video, tmp_path, "part2")
    assert clip1.success and clip2.success

    target = tmp_path / "merged"
    target.mkdir()

    result = MoviePyConcatenator().concatenate([clip1, clip2], title="joined", target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0
    assert result.output_path.name == "joined.mp4"


def test_concatenate_requires_at_least_two_successful_clips(tmp_path: Path) -> None:
    only_one = ClipResult(title="solo", output_path=tmp_path / "solo.mp4", success=True)
    target = tmp_path / "merged"
    target.mkdir()

    result = MoviePyConcatenator().concatenate([only_one], title="joined", target=target)

    assert result.success is False
