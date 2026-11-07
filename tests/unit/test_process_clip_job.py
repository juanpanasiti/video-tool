"""Unit tests for application/use_cases/process_clip_job.py."""

from __future__ import annotations

from pathlib import Path

from pytest_mock import MockerFixture

from application.ports import IAudioExtractor, IClipper
from application.use_cases.process_clip_job import ProcessClipJob
from domain.models import (
    AudioResult,
    ClipInterval,
    ClipJob,
    ClipResult,
    VideoFile,
)


def _make_job(audio_only: bool) -> ClipJob:
    video = VideoFile(name="movie", extension=".mp4", path=Path("/videos/movie.mp4"))
    interval = ClipInterval(title="clip", audio_only=audio_only)
    return ClipJob(id="job-1", video=video, interval=interval)


def test_routes_video_job_to_clipper(mocker: MockerFixture) -> None:
    clipper = mocker.Mock(spec=IClipper)
    extractor = mocker.Mock(spec=IAudioExtractor)
    expected = ClipResult(title="clip", output_path=Path("/out/clip.mp4"), success=True)
    clipper.cut.return_value = expected
    job = _make_job(audio_only=False)
    target = Path("/out")

    result = ProcessClipJob(clipper=clipper, extractor=extractor).execute(job=job, target=target)

    assert result is expected
    clipper.cut.assert_called_once_with(
        video=job.video, interval=job.interval, target=target, on_progress=None
    )
    extractor.extract.assert_not_called()


def test_routes_audio_job_to_extractor(mocker: MockerFixture) -> None:
    clipper = mocker.Mock(spec=IClipper)
    extractor = mocker.Mock(spec=IAudioExtractor)
    expected = AudioResult(title="clip", output_path=Path("/out/clip.mp3"), success=True)
    extractor.extract.return_value = expected
    job = _make_job(audio_only=True)
    target = Path("/out")

    result = ProcessClipJob(clipper=clipper, extractor=extractor).execute(job=job, target=target)

    assert result is expected
    extractor.extract.assert_called_once_with(video=job.video, interval=job.interval, target=target)
    clipper.cut.assert_not_called()


def test_forwards_progress_callback_for_video_jobs(mocker: MockerFixture) -> None:
    clipper = mocker.Mock(spec=IClipper)
    extractor = mocker.Mock(spec=IAudioExtractor)
    clipper.cut.return_value = ClipResult(
        title="clip", output_path=Path("/out/clip.mp4"), success=True
    )
    job = _make_job(audio_only=False)
    on_progress = mocker.Mock()

    ProcessClipJob(clipper=clipper, extractor=extractor).execute(
        job=job, target=Path("/out"), on_progress=on_progress
    )

    clipper.cut.assert_called_once_with(
        video=job.video, interval=job.interval, target=Path("/out"), on_progress=on_progress
    )


def test_resolves_and_creates_subfolder_under_target(mocker: MockerFixture, tmp_path: Path) -> None:
    clipper = mocker.Mock(spec=IClipper)
    extractor = mocker.Mock(spec=IAudioExtractor)
    clipper.cut.return_value = ClipResult(
        title="clip", output_path=tmp_path / "sub" / "clip.mp4", success=True
    )
    video = VideoFile(name="movie", extension=".mp4", path=tmp_path / "movie.mp4")
    interval = ClipInterval(title="clip", subfolder="sub")
    job = ClipJob(id="job-1", video=video, interval=interval)

    ProcessClipJob(clipper=clipper, extractor=extractor).execute(job=job, target=tmp_path)

    expected_target = tmp_path / "sub"
    assert expected_target.is_dir()
    clipper.cut.assert_called_once_with(
        video=job.video, interval=job.interval, target=expected_target, on_progress=None
    )


def test_no_subfolder_uses_target_as_is_without_creating_it(mocker: MockerFixture) -> None:
    clipper = mocker.Mock(spec=IClipper)
    extractor = mocker.Mock(spec=IAudioExtractor)
    clipper.cut.return_value = ClipResult(
        title="clip", output_path=Path("/out/clip.mp4"), success=True
    )
    job = _make_job(audio_only=False)
    target = Path("/nonexistent-target-should-not-be-created")

    ProcessClipJob(clipper=clipper, extractor=extractor).execute(job=job, target=target)

    assert not target.exists()
    clipper.cut.assert_called_once_with(
        video=job.video, interval=job.interval, target=target, on_progress=None
    )
