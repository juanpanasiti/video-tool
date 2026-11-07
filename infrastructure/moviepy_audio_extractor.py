"""Concrete implementation of IAudioExtractor using moviepy v2."""

from __future__ import annotations

import logging
from pathlib import Path

from application.ports import IAudioExtractor
from domain.exceptions import ClipProcessingError
from domain.models import AudioResult, ClipInterval, Quality, VideoFile
from infrastructure.filename_utils import sanitize_filename

logger = logging.getLogger("video_tool.moviepy_audio_extractor")


class MoviePyAudioExtractor(IAudioExtractor):
    """Extracts audio from a video clip and writes it as an MP3 file."""

    def extract(
        self,
        video: VideoFile,
        interval: ClipInterval,
        target: Path,
    ) -> AudioResult:
        """Extract audio from *video* within *interval* and write an MP3 to *target*.

        Output filename: ``<video.name> - <interval.title>.mp3``
        """
        safe_title = sanitize_filename(interval.title)
        output_name = f"{video.name} - {safe_title}.mp3"
        output_path = target / output_name

        try:
            from moviepy import VideoFileClip

            with VideoFileClip(str(video.path)) as clip:
                if clip.audio is None:
                    return AudioResult(
                        title=interval.title,
                        output_path=output_path,
                        success=False,
                        error="The video file has no audio track.",
                    )

                subclip = clip.subclipped(interval.start_seconds, interval.end_seconds)

                _BITRATE_BY_QUALITY: dict[Quality, str] = {
                    Quality.HIGH: "320k",
                    Quality.MEDIUM: "192k",
                    Quality.LOW: "128k",
                }
                audio_bitrate = _BITRATE_BY_QUALITY[interval.quality]

                subclip.audio.write_audiofile(
                    str(output_path),
                    codec="libmp3lame",
                    bitrate=audio_bitrate,
                    logger=None,
                )

        except Exception as exc:
            logger.exception("Failed to extract audio for '%s' from %s", interval.title, video.path)
            return AudioResult(
                title=interval.title,
                output_path=output_path,
                success=False,
                error=str(ClipProcessingError(interval.title, str(exc))),
            )

        return AudioResult(
            title=interval.title,
            output_path=output_path,
            success=True,
        )
