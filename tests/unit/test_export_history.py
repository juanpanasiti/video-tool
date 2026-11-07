"""Unit tests for application/use_cases/export_history.py."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from application.use_cases.export_history import format_history_csv, format_history_json
from domain.models import ClipInterval, ClipJob, ClipResult, JobStatus, VideoFile


def _make_video(path: Path) -> VideoFile:
    return VideoFile(name=path.stem, extension=path.suffix, path=path)


def _done_job(tmp_path: Path, title: str) -> ClipJob:
    video = _make_video(tmp_path / "a.mp4")
    job = ClipJob(id=title, video=video, interval=ClipInterval(title=title), status=JobStatus.DONE)
    job.result = ClipResult(title=title, output_path=tmp_path / f"{title}.mp4", success=True)
    return job


def _error_job(tmp_path: Path, title: str) -> ClipJob:
    video = _make_video(tmp_path / "a.mp4")
    job = ClipJob(id=title, video=video, interval=ClipInterval(title=title), status=JobStatus.ERROR)
    job.result = ClipResult(
        title=title, output_path=tmp_path / f"{title}.mp4", success=False, error="boom"
    )
    return job


def test_format_history_csv_includes_done_and_error_jobs(tmp_path: Path) -> None:
    jobs = [_done_job(tmp_path, "clip1"), _error_job(tmp_path, "clip2")]

    csv_text = format_history_csv(jobs)

    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0] == ["title", "video", "status", "output_path", "error"]
    assert rows[1][0] == "clip1"
    assert rows[1][2] == "done"
    assert rows[2][0] == "clip2"
    assert rows[2][4] == "boom"


def test_format_history_csv_excludes_pending_and_processing_jobs(tmp_path: Path) -> None:
    video = _make_video(tmp_path / "a.mp4")
    pending = ClipJob(id="p", video=video, interval=ClipInterval(title="pending"))

    csv_text = format_history_csv([pending])

    rows = list(csv.reader(io.StringIO(csv_text)))
    assert len(rows) == 1  # header only


def test_format_history_json_round_trips(tmp_path: Path) -> None:
    jobs = [_done_job(tmp_path, "clip1")]

    json_text = format_history_json(jobs)
    data = json.loads(json_text)

    assert data == [
        {
            "title": "clip1",
            "video": "a.mp4",
            "status": "done",
            "output_path": str(tmp_path / "clip1.mp4"),
            "error": None,
        }
    ]
