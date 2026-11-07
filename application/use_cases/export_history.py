"""Use case: format the finished-job history for export (CSV or JSON).

Pure formatting logic — no file I/O. Callers write the returned string wherever
appropriate for their layer.
"""

from __future__ import annotations

import csv
import io
import json

from domain.models import ClipJob, JobStatus


def format_history_csv(jobs: list[ClipJob]) -> str:
    """Return a CSV string with one row per finished (DONE/ERROR) job."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "video", "status", "output_path", "error"])
    for job in _finished(jobs):
        result = job.result
        output_path = str(result.output_path) if result is not None else ""
        error = result.error if result is not None and result.error else ""
        writer.writerow([job.interval.title, job.video.display_name, job.status.value, output_path, error])
    return buffer.getvalue()


def format_history_json(jobs: list[ClipJob]) -> str:
    """Return a JSON string (array of objects) with one entry per finished job."""
    entries = []
    for job in _finished(jobs):
        result = job.result
        entries.append(
            {
                "title": job.interval.title,
                "video": job.video.display_name,
                "status": job.status.value,
                "output_path": str(result.output_path) if result is not None else None,
                "error": result.error if result is not None else None,
            }
        )
    return json.dumps(entries, indent=2, ensure_ascii=False)


def _finished(jobs: list[ClipJob]) -> list[ClipJob]:
    return [j for j in jobs if j.status in (JobStatus.DONE, JobStatus.ERROR)]
