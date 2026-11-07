"""Unit tests for presentation/web/queue_worker.py::QueueWorker."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from pytest_mock import MockerFixture

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
from domain.models import AppConfig, ClipInterval, ClipJob, ClipResult, JobStatus, VideoFile
from presentation.web.queue_worker import QueueWorker
from presentation.web.state import AppState


def _make_state(mocker: MockerFixture, tmp_path: Path) -> AppState:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    return AppState(
        config=AppConfig(source=source, target=target),
        repository=mocker.Mock(spec=IVideoRepository),
        clipper=mocker.Mock(spec=IClipper),
        audio_extractor=mocker.Mock(spec=IAudioExtractor),
        preferences_store=mocker.Mock(spec=IPreferencesStore),
        notifier=mocker.Mock(spec=INotifier),
        thumbnailer=mocker.Mock(spec=IThumbnailer),
        video_metadata=mocker.Mock(spec=IVideoMetadata),
        concatenator=mocker.Mock(spec=IConcatenator),
    )


def _make_video(path: Path) -> VideoFile:
    return VideoFile(name=path.stem, extension=path.suffix, path=path)


async def _run_until(worker: QueueWorker, predicate, timeout: float = 2.0) -> None:
    """Drive the worker's queue until *predicate* is true or *timeout* elapses."""
    task = asyncio.create_task(worker.run_forever())
    try:
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_processes_single_job_to_done(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    process_uc = mocker.Mock()
    process_uc.execute.return_value = ClipResult(
        title="clip", output_path=tmp_path / "out.mp4", success=True
    )
    worker = QueueWorker(state, process_uc)
    worker.notify()

    await _run_until(worker, lambda: job.status in (JobStatus.DONE, JobStatus.ERROR))

    assert job.status == JobStatus.DONE
    assert job.progress == 1.0
    process_uc.execute.assert_called_once()


async def test_failed_result_marks_job_error(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    process_uc = mocker.Mock()
    process_uc.execute.return_value = ClipResult(
        title="clip", output_path=tmp_path / "out.mp4", success=False, error="boom"
    )
    worker = QueueWorker(state, process_uc)
    worker.notify()

    await _run_until(worker, lambda: job.status in (JobStatus.DONE, JobStatus.ERROR))

    assert job.status == JobStatus.ERROR


async def test_processes_jobs_in_fifo_order(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job1 = state.enqueue(video, ClipInterval(title="clip1"))
    job2 = state.enqueue(video, ClipInterval(title="clip2"))

    processed_order: list[str] = []

    def fake_execute(job: ClipJob, target: Path, on_progress=None) -> ClipResult:
        processed_order.append(job.id)
        return ClipResult(title=job.interval.title, output_path=target / "out.mp4", success=True)

    process_uc = mocker.Mock()
    process_uc.execute.side_effect = fake_execute
    worker = QueueWorker(state, process_uc)
    worker.notify()

    await _run_until(worker, lambda: job2.status in (JobStatus.DONE, JobStatus.ERROR))

    assert processed_order == [job1.id, job2.id]


async def test_status_changed_callback_fires_on_start_and_finish(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    process_uc = mocker.Mock()
    process_uc.execute.return_value = ClipResult(
        title="clip", output_path=tmp_path / "out.mp4", success=True
    )
    worker = QueueWorker(state, process_uc)
    statuses_seen: list[JobStatus] = []
    worker.on_status_changed(lambda j: statuses_seen.append(j.status))
    worker.notify()

    await _run_until(worker, lambda: job.status in (JobStatus.DONE, JobStatus.ERROR))

    assert JobStatus.PROCESSING in statuses_seen
    assert statuses_seen[-1] == JobStatus.DONE


async def test_paused_worker_does_not_pick_up_pending_jobs(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.enqueue(video, ClipInterval(title="clip"))

    process_uc = mocker.Mock()
    worker = QueueWorker(state, process_uc)
    worker.pause()
    worker.notify()

    task = asyncio.create_task(worker.run_forever())
    try:
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    process_uc.execute.assert_not_called()


async def test_resume_lets_paused_worker_process_pending_job(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    process_uc = mocker.Mock()
    process_uc.execute.return_value = ClipResult(
        title="clip", output_path=tmp_path / "out.mp4", success=True
    )
    worker = QueueWorker(state, process_uc)
    worker.pause()

    task = asyncio.create_task(worker.run_forever())
    try:
        await asyncio.sleep(0.05)
        assert job.status == JobStatus.PENDING

        worker.resume()
        async with asyncio.timeout(2.0):
            while job.status not in (JobStatus.DONE, JobStatus.ERROR):
                await asyncio.sleep(0)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert job.status == JobStatus.DONE

