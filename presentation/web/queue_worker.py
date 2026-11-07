"""Background FIFO worker that drains AppState's clip job queue one job at a time.

Runs as an asyncio task on the NiceGUI event loop so the UI stays responsive
while clips for different videos are queued and processed strictly in order.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from nicegui import run

from application.use_cases.process_clip_job import ProcessClipJob
from domain.models import ClipJob, JobStatus
from presentation.web.state import AppState

logger = logging.getLogger("video_tool.queue_worker")


class QueueWorker:
    """Consumes PENDING ClipJobs from AppState.jobs in FIFO order, one at a time."""

    def __init__(self, state: AppState, process_uc: ProcessClipJob) -> None:
        self._state = state
        self._process_uc = process_uc
        self._wakeup = asyncio.Event()
        self._on_status_changed: Callable[[ClipJob], None] | None = None
        self._on_progress: Callable[[ClipJob], None] | None = None
        self.paused = False

    def pause(self) -> None:
        """Stop picking up new PENDING jobs. Does not interrupt an in-flight job."""
        self.paused = True

    def resume(self) -> None:
        """Resume picking up PENDING jobs and wake the worker immediately."""
        self.paused = False
        self.notify()

    def on_status_changed(self, callback: Callable[[ClipJob], None]) -> None:
        """Register a UI callback invoked when a job is added, starts, or finishes.

        Fires rarely (once per job transition) so the callback may safely
        rebuild whole UI panels.
        """
        self._on_status_changed = callback

    def on_progress(self, callback: Callable[[ClipJob], None]) -> None:
        """Register a UI callback invoked on every frame-level progress tick.

        Fires many times per second while a clip is encoding — the callback
        MUST be cheap (e.g. update a single progress bar's value) and must
        NOT rebuild UI panels or hit the file system.
        """
        self._on_progress = callback

    def notify(self) -> None:
        """Wake the worker up after a new job was enqueued."""
        self._wakeup.set()

    async def run_forever(self) -> None:
        """Drain the queue forever, sleeping when there is nothing pending."""
        while True:
            job = self._next_pending()
            if job is None:
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            await self._process(job)

    def _next_pending(self) -> ClipJob | None:
        if self.paused:
            return None
        return next((j for j in self._state.jobs if j.status == JobStatus.PENDING), None)

    async def _process(self, job: ClipJob) -> None:
        job.status = JobStatus.PROCESSING
        logger.info("Job %s started: %s", job.id, job.interval.title)
        self._emit_status(job)

        loop = asyncio.get_running_loop()

        def on_progress(current: float, total: float) -> None:
            loop.call_soon_threadsafe(self._update_progress, job, current, total)

        result = await run.io_bound(
            self._process_uc.execute,
            job=job,
            target=self._state.config.target,
            on_progress=on_progress,
        )
        assert result is not None  # io_bound only returns None if the callback itself does
        job.result = result
        job.progress = 1.0
        job.status = JobStatus.DONE if result.success else JobStatus.ERROR
        if result.success:
            logger.info("Job %s finished: %s", job.id, result.output_path)
        else:
            logger.error("Job %s failed: %s", job.id, result.error)
        self._emit_status(job)

    def _update_progress(self, job: ClipJob, current: float, total: float) -> None:
        job.progress = current / total if total else 0.0
        if self._on_progress is not None:
            self._on_progress(job)

    def _emit_status(self, job: ClipJob) -> None:
        if self._on_status_changed is not None:
            self._on_status_changed(job)
