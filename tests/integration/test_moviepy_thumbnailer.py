"""Integration tests for infrastructure/moviepy_thumbnailer.py (real ffmpeg decode)."""

from __future__ import annotations

from pathlib import Path

from infrastructure.moviepy_thumbnailer import MoviePyThumbnailer
from infrastructure.video_repository import VideoRepository


def test_get_thumbnail_creates_image_file(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    cache_dir = tmp_path / "thumbs"

    thumb_path = MoviePyThumbnailer().get_thumbnail(video, cache_dir)

    assert thumb_path.exists()
    assert thumb_path.suffix == ".jpg"
    assert thumb_path.stat().st_size > 0


def test_get_thumbnail_is_cached_on_second_call(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    cache_dir = tmp_path / "thumbs"
    thumbnailer = MoviePyThumbnailer()

    first = thumbnailer.get_thumbnail(video, cache_dir)
    mtime_before = first.stat().st_mtime
    second = thumbnailer.get_thumbnail(video, cache_dir)

    assert first == second
    assert second.stat().st_mtime == mtime_before
