"""Unit tests for presentation/web/state.py::AppState."""

from __future__ import annotations

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
from domain.models import AppConfig, ClipInterval, JobStatus, VideoFile
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


def test_enqueue_appends_pending_job(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    interval = ClipInterval(title="clip")

    job = state.enqueue(video, interval)

    assert job.status == JobStatus.PENDING
    assert state.jobs == [job]


def test_enqueue_keeps_fifo_order_across_videos(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video_a = _make_video(tmp_path / "a.mp4")
    video_b = _make_video(tmp_path / "b.mp4")

    job1 = state.enqueue(video_a, ClipInterval(title="clip1"))
    job2 = state.enqueue(video_b, ClipInterval(title="clip2"))
    job3 = state.enqueue(video_a, ClipInterval(title="clip3"))

    assert state.jobs == [job1, job2, job3]


def test_cancel_removes_pending_job(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    removed = state.cancel(job.id)

    assert removed is True
    assert state.jobs == []


def test_cancel_does_not_remove_processing_job(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))
    job.status = JobStatus.PROCESSING

    removed = state.cancel(job.id)

    assert removed is False
    assert state.jobs == [job]


def test_cancel_unknown_id_returns_false(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)

    assert state.cancel("missing") is False


def test_is_video_busy_true_for_pending_or_processing(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.enqueue(video, ClipInterval(title="clip"))

    assert state.is_video_busy(video) is True


def test_is_video_busy_false_when_no_jobs(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")

    assert state.is_video_busy(video) is False


def test_is_video_busy_false_once_job_finished(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))
    job.status = JobStatus.DONE

    assert state.is_video_busy(video) is False


def test_retry_reenqueues_error_job_as_new_pending_job(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))
    job.status = JobStatus.ERROR

    retried = state.retry(job.id)

    assert retried is not None
    assert retried.id != job.id
    assert retried.status == JobStatus.PENDING
    assert retried.video == job.video
    assert retried.interval == job.interval
    assert state.jobs == [job, retried]


def test_retry_returns_none_for_non_error_job(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job = state.enqueue(video, ClipInterval(title="clip"))

    assert state.retry(job.id) is None
    assert state.jobs == [job]


def test_retry_returns_none_for_unknown_id(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)

    assert state.retry("missing") is None


def test_move_job_up_swaps_with_previous_pending(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job1 = state.enqueue(video, ClipInterval(title="clip1"))
    job2 = state.enqueue(video, ClipInterval(title="clip2"))

    moved = state.move_job(job2.id, "up")

    assert moved is True
    assert state.jobs == [job2, job1]


def test_move_job_down_swaps_with_next_pending(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job1 = state.enqueue(video, ClipInterval(title="clip1"))
    job2 = state.enqueue(video, ClipInterval(title="clip2"))

    moved = state.move_job(job1.id, "down")

    assert moved is True
    assert state.jobs == [job2, job1]


def test_move_job_up_at_top_is_noop(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job1 = state.enqueue(video, ClipInterval(title="clip1"))

    assert state.move_job(job1.id, "up") is False
    assert state.jobs == [job1]


def test_move_job_skips_non_pending_jobs(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    job1 = state.enqueue(video, ClipInterval(title="clip1"))
    job2 = state.enqueue(video, ClipInterval(title="clip2"))
    job3 = state.enqueue(video, ClipInterval(title="clip3"))
    job2.status = JobStatus.PROCESSING

    # job3 is the next PENDING job after job1 among PENDING jobs, ignoring job2.
    moved = state.move_job(job3.id, "up")

    assert moved is True
    assert state.jobs == [job3, job2, job1]


def test_move_job_returns_false_for_unknown_id(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)

    assert state.move_job("missing", "up") is False


def test_stage_accumulates_intervals_per_video(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")

    state.stage(video, ClipInterval(title="clip1"))
    state.stage(video, ClipInterval(title="clip2"))

    assert [i.title for i in state.staged[video.path]] == ["clip1", "clip2"]


def test_unstage_removes_by_index(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.stage(video, ClipInterval(title="clip1"))
    state.stage(video, ClipInterval(title="clip2"))

    state.unstage(video, 0)

    assert [i.title for i in state.staged[video.path]] == ["clip2"]


def test_unstage_removes_empty_list_entry(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.stage(video, ClipInterval(title="clip1"))

    state.unstage(video, 0)

    assert video.path not in state.staged


def test_unstage_ignores_out_of_range_index(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.stage(video, ClipInterval(title="clip1"))

    state.unstage(video, 5)

    assert [i.title for i in state.staged[video.path]] == ["clip1"]


def test_enqueue_staged_creates_jobs_and_clears_staging(mocker: MockerFixture, tmp_path: Path) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")
    state.stage(video, ClipInterval(title="clip1"))
    state.stage(video, ClipInterval(title="clip2"))

    jobs = state.enqueue_staged(video)

    assert [j.interval.title for j in jobs] == ["clip1", "clip2"]
    assert all(j.status == JobStatus.PENDING for j in jobs)
    assert state.jobs == jobs
    assert video.path not in state.staged


def test_enqueue_staged_returns_empty_list_when_nothing_staged(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    state = _make_state(mocker, tmp_path)
    video = _make_video(tmp_path / "a.mp4")

    assert state.enqueue_staged(video) == []


