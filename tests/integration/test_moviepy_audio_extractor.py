"""Integration tests for infrastructure/moviepy_audio_extractor.py (real ffmpeg decode)."""

from __future__ import annotations

from pathlib import Path

from domain.models import ClipInterval, Quality
from infrastructure.moviepy_audio_extractor import MoviePyAudioExtractor
from infrastructure.video_repository import VideoRepository


def test_extract_produces_valid_mp3(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="audio clip")
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyAudioExtractor().extract(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.name == "sample - audio clip.mp3"
    assert result.output_path.stat().st_size > 0


def test_extract_respects_quality_preset(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="clip", quality=Quality.LOW)
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyAudioExtractor().extract(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
