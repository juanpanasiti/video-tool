"""Concrete implementation of IVideoRepository.

Scans a folder on the local file system for supported video files.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from application.ports import IVideoRepository
from domain.exceptions import NoVideosFoundError
from domain.models import VideoFile

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".mov", ".avi", ".mkv", ".webm"}
)

# Suffix appended by moviepy to temporary audio files during video encoding.
_MOVIEPY_TEMP_SUFFIX = "TEMP_MPY_wvf_snd.mp3"


def detect_processing_video_names(
    search_dir: Path,
    candidate_names: Iterable[str],
) -> frozenset[str]:
    """Return the subset of *candidate_names* that have a moviepy temp audio
    file present in *search_dir*.

    Moviepy writes a temp file like ``{video} - {clip}TEMP_MPY_wvf_snd.mp3``
    while encoding.  Its presence means another process is currently cutting
    that video.
    """
    try:
        temp_file_names = {
            entry.name
            for entry in search_dir.iterdir()
            if entry.is_file() and entry.name.endswith(_MOVIEPY_TEMP_SUFFIX)
        }
    except OSError:
        return frozenset()

    return frozenset(
        name for name in candidate_names
        if any(tmp.startswith(name) for tmp in temp_file_names)
    )


class VideoRepository(IVideoRepository):
    """Scans a directory and returns all supported video files.

    Caches the scan per *source* directory, keyed by the directory's mtime,
    so repeated calls (e.g. from a `@ui.refreshable` panel re-rendering)
    don't re-hit the file system unless files were actually added/removed.
    """

    def __init__(self) -> None:
        self._cache: dict[Path, tuple[float, list[VideoFile]]] = {}

    def list_videos(self, source: Path) -> list[VideoFile]:
        """Return all supported video files found directly inside *source*.

        Raises:
            NoVideosFoundError: if no matching files are found.
        """
        mtime = source.stat().st_mtime
        cached = self._cache.get(source)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        videos: list[VideoFile] = []

        for entry in sorted(source.iterdir(), reverse=True):
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                videos.append(
                    VideoFile(
                        name=entry.stem,
                        extension=entry.suffix.lower(),
                        path=entry.resolve(),
                    )
                )

        if not videos:
            raise NoVideosFoundError(str(source))

        self._cache[source] = (mtime, videos)
        return videos

    def detect_processing(self, search_dir: Path, candidate_names: Iterable[str]) -> frozenset[str]:
        return detect_processing_video_names(search_dir, candidate_names)
