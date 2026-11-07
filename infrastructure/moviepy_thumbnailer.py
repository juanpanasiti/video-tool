"""Concrete implementation of IThumbnailer using moviepy to grab a single frame."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from application.ports import IThumbnailer
from domain.models import VideoFile

logger = logging.getLogger("video_tool.moviepy_thumbnailer")


class MoviePyThumbnailer(IThumbnailer):
    """Extracts one frame per video as a cached JPEG thumbnail.

    Cache key is the video's absolute path + mtime, so a re-encoded/replaced
    file gets a fresh thumbnail instead of serving a stale cached one.
    """

    def get_thumbnail(self, video: VideoFile, cache_dir: Path) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        mtime = int(video.path.stat().st_mtime)
        key = hashlib.sha1(f"{video.path}|{mtime}".encode()).hexdigest()
        thumb_path = cache_dir / f"{key}.jpg"
        if thumb_path.exists():
            return thumb_path

        from moviepy import VideoFileClip

        with VideoFileClip(str(video.path)) as clip:
            t = min(1.0, clip.duration / 2) if clip.duration else 0.0
            clip.save_frame(str(thumb_path), t=t)
        return thumb_path
