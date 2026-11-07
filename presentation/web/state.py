"""Shared mutable state for the NiceGUI presentation layer.

The app runs as a single native window with a single client, so a plain
module-level instance (created once in ``app.run()``) is enough to replace
the per-App attributes the Textual TUI used to hold.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from application.ports import (
    IAudioExtractor,
    IClipper,
    IConcatenator,
    INotifier,
    IPreferencesStore,
    IThumbnailer,
    IVideoMetadata,
    IVideoRepository,
)
from domain.models import AppConfig, ClipInterval, ClipJob, JobStatus, UserPreferences, VideoFile


@dataclass
class AppState:
    """Cross-page state plus the infrastructure instances injected at startup.

    ``jobs`` is the single FIFO processing queue shared by every video: clips
    accepted for different videos are appended to the same list and drained
    in order by the background QueueWorker, regardless of which video is
    currently selected in the form.
    """

    config: AppConfig
    repository: IVideoRepository
    clipper: IClipper
    audio_extractor: IAudioExtractor
    preferences_store: IPreferencesStore
    notifier: INotifier
    thumbnailer: IThumbnailer
    video_metadata: IVideoMetadata
    concatenator: IConcatenator
    preferences: UserPreferences = field(default_factory=UserPreferences)
    selected_video: VideoFile | None = None
    jobs: list[ClipJob] = field(default_factory=list)
    video_filter: str = ""
    show_player: bool = True
    staged: dict[Path, list[ClipInterval]] = field(default_factory=dict)

    def stage(self, video: VideoFile, interval: ClipInterval) -> None:
        """Add *interval* to the batch of not-yet-enqueued clips for *video*."""
        self.staged.setdefault(video.path, []).append(interval)

    def unstage(self, video: VideoFile, index: int) -> None:
        """Remove the staged interval at *index* for *video*, if present."""
        items = self.staged.get(video.path)
        if items is not None and 0 <= index < len(items):
            del items[index]
            if not items:
                del self.staged[video.path]

    def enqueue_staged(self, video: VideoFile) -> list[ClipJob]:
        """Enqueue every staged interval for *video* as a new PENDING job, then clear it."""
        items = self.staged.pop(video.path, [])
        return [self.enqueue(video, interval) for interval in items]

    def enqueue(self, video: VideoFile, interval: ClipInterval) -> ClipJob:
        """Create a PENDING job for *interval* on *video* and queue it."""
        job = ClipJob(id=str(uuid.uuid4()), video=video, interval=interval)
        self.jobs.append(job)
        return job

    def cancel(self, job_id: str) -> bool:
        """Remove a still-PENDING job from the queue. Returns True if removed."""
        for i, job in enumerate(self.jobs):
            if job.id == job_id and job.status == JobStatus.PENDING:
                del self.jobs[i]
                return True
        return False

    def retry(self, job_id: str) -> ClipJob | None:
        """Re-enqueue a failed job's video/interval as a new PENDING job."""
        for job in self.jobs:
            if job.id == job_id and job.status == JobStatus.ERROR:
                return self.enqueue(job.video, job.interval)
        return None

    def move_job(self, job_id: str, direction: Literal["up", "down"]) -> bool:
        """Move a PENDING job earlier/later relative to other PENDING jobs.

        Only reorders among still-PENDING jobs (a job already PROCESSING/DONE/
        ERROR can't move, and doesn't block other PENDING jobs from reordering
        around it). Returns True if the job moved.
        """
        pending_indices = [i for i, j in enumerate(self.jobs) if j.status == JobStatus.PENDING]
        try:
            pos = next(p for p, i in enumerate(pending_indices) if self.jobs[i].id == job_id)
        except StopIteration:
            return False

        other_pos = pos - 1 if direction == "up" else pos + 1
        if other_pos < 0 or other_pos >= len(pending_indices):
            return False

        i, j = pending_indices[pos], pending_indices[other_pos]
        self.jobs[i], self.jobs[j] = self.jobs[j], self.jobs[i]
        return True

    def is_video_busy(self, video: VideoFile) -> bool:
        """True if *video* has a job that is still pending or processing."""
        return any(
            job.video.path == video.path and job.status in (JobStatus.PENDING, JobStatus.PROCESSING)
            for job in self.jobs
        )

