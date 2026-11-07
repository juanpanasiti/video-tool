"""Concrete implementation of IConcatenator using moviepy v2."""

from __future__ import annotations

import logging
from pathlib import Path

from application.ports import IConcatenator
from domain.exceptions import ClipProcessingError
from domain.models import ClipResult
from infrastructure.filename_utils import sanitize_filename

logger = logging.getLogger("video_tool.moviepy_concatenator")


class MoviePyConcatenator(IConcatenator):
    """Joins several clip files into one using moviepy's concatenate_videoclips."""

    def concatenate(self, clips: list[ClipResult], title: str, target: Path) -> ClipResult:
        safe_title = sanitize_filename(title)
        successful = [c for c in clips if c.success]
        extension = successful[0].output_path.suffix if successful else ".mp4"
        output_path = target / f"{safe_title}{extension}"

        if len(successful) < 2:
            return ClipResult(
                title=title,
                output_path=output_path,
                success=False,
                error=str(ClipProcessingError(title, "Se necesitan al menos 2 clips exitosos para unir.")),
            )

        try:
            from moviepy import VideoFileClip, concatenate_videoclips

            source_clips = [VideoFileClip(str(c.output_path)) for c in successful]
            try:
                joined = concatenate_videoclips(source_clips)
                try:
                    joined.write_videofile(str(output_path), logger=None)
                finally:
                    joined.close()
            finally:
                for source_clip in source_clips:
                    source_clip.close()
        except Exception as exc:
            logger.exception("Failed to concatenate clips into '%s'", title)
            return ClipResult(
                title=title,
                output_path=output_path,
                success=False,
                error=str(ClipProcessingError(title, str(exc))),
            )

        return ClipResult(title=title, output_path=output_path, success=True)
