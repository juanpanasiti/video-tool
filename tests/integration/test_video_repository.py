"""Integration tests for infrastructure/video_repository.py using real temp-dir files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from domain.exceptions import NoVideosFoundError
from infrastructure.video_repository import VideoRepository, detect_processing_video_names


def _touch(path: Path) -> None:
    path.write_bytes(b"")


class TestVideoRepositoryListVideos:
    def test_lists_supported_extensions_only(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mp4")
        _touch(tmp_path / "b.mov")
        _touch(tmp_path / "notes.txt")
        _touch(tmp_path / "c.MKV")  # extension matching is case-insensitive, normalized to lowercase

        videos = VideoRepository().list_videos(tmp_path)

        names = {v.display_name for v in videos}
        assert names == {"a.mp4", "b.mov", "c.mkv"}

    def test_ignores_subdirectories(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mp4")
        (tmp_path / "subfolder").mkdir()
        _touch(tmp_path / "subfolder" / "b.mp4")

        videos = VideoRepository().list_videos(tmp_path)

        assert [v.display_name for v in videos] == ["a.mp4"]

    def test_raises_when_no_videos_found(self, tmp_path: Path) -> None:
        _touch(tmp_path / "notes.txt")

        with pytest.raises(NoVideosFoundError):
            VideoRepository().list_videos(tmp_path)

    def test_video_path_is_resolved_absolute(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mp4")

        videos = VideoRepository().list_videos(tmp_path)

        assert videos[0].path.is_absolute()
        assert videos[0].path == (tmp_path / "a.mp4").resolve()

    def test_returns_cached_result_while_directory_mtime_is_unchanged(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mp4")
        repo = VideoRepository()
        first = repo.list_videos(tmp_path)
        assert [v.display_name for v in first] == ["a.mp4"]

        # Add a file but pin the directory mtime back to its pre-add value: the
        # repository should keep serving the cached (stale) listing.
        dir_mtime = tmp_path.stat().st_mtime
        _touch(tmp_path / "b.mp4")
        os.utime(tmp_path, (dir_mtime, dir_mtime))

        cached = repo.list_videos(tmp_path)
        assert [v.display_name for v in cached] == ["a.mp4"]

    def test_invalidates_cache_once_directory_mtime_advances(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mp4")
        repo = VideoRepository()
        repo.list_videos(tmp_path)

        _touch(tmp_path / "b.mp4")
        os.utime(tmp_path, None)  # bump mtime to "now", simulating a real fs change

        fresh = repo.list_videos(tmp_path)
        assert {v.display_name for v in fresh} == {"a.mp4", "b.mp4"}


class TestDetectProcessingVideoNames:
    def test_detects_video_with_temp_audio_file(self, tmp_path: Path) -> None:
        _touch(tmp_path / "movie - clip1TEMP_MPY_wvf_snd.mp3")

        busy = detect_processing_video_names(tmp_path, ["movie", "other"])

        assert busy == {"movie"}

    def test_returns_empty_when_no_temp_files(self, tmp_path: Path) -> None:
        busy = detect_processing_video_names(tmp_path, ["movie"])

        assert busy == frozenset()

    def test_returns_empty_for_missing_directory(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing"

        busy = detect_processing_video_names(missing, ["movie"])

        assert busy == frozenset()
