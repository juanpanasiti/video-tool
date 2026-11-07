"""Integration tests for infrastructure/moviepy_video_metadata.py (real ffmpeg parse)."""

from __future__ import annotations

from pathlib import Path

from infrastructure.moviepy_video_metadata import MoviePyVideoMetadata
from infrastructure.video_repository import VideoRepository


def test_get_duration_returns_approximate_duration(sample_video: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]

    duration = MoviePyVideoMetadata().get_duration(video)

    assert 1.5 <= duration <= 2.5  # sample_video fixture is a 2s clip
