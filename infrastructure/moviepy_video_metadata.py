"""Concrete implementation of IVideoMetadata using moviepy (metadata parse only)."""

from __future__ import annotations

from application.ports import IVideoMetadata
from domain.models import VideoFile


class MoviePyVideoMetadata(IVideoMetadata):
    """Reads a video's duration via moviepy/ffmpeg header parsing (no frame decode)."""

    def get_duration(self, video: VideoFile) -> float:
        from moviepy import VideoFileClip

        with VideoFileClip(str(video.path)) as clip:
            return float(clip.duration)
