"""Use case: process a single queued ClipJob (video cut or audio extraction)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from application.ports import IAudioExtractor, IClipper
from domain.models import AudioResult, ClipJob, ClipResult


class ProcessClipJob:
    """Execute one ClipJob, routing it to the clipper or the audio extractor."""

    def __init__(self, clipper: IClipper, extractor: IAudioExtractor) -> None:
        self._clipper = clipper
        self._extractor = extractor

    def execute(
        self,
        job: ClipJob,
        target: Path,
        on_progress: Callable[[float, float], None] | None = None,
    ) -> ClipResult | AudioResult:
        """Run *job* against *target* and return its result.

        Audio-only jobs report no progress; video cuts report progress via
        *on_progress* as frames are encoded.

        If the job's interval requests a subfolder, it is resolved under
        *target* and created if it doesn't exist yet. *target* itself is
        assumed to already exist (validated by AppConfig) and is never
        created here.
        """
        if job.interval.subfolder:
            resolved_target = target / job.interval.subfolder
            resolved_target.mkdir(parents=True, exist_ok=True)
        else:
            resolved_target = target

        if job.interval.audio_only:
            return self._extractor.extract(
                video=job.video, interval=job.interval, target=resolved_target
            )
        return self._clipper.cut(
            video=job.video, interval=job.interval, target=resolved_target, on_progress=on_progress
        )
