"""Domain models (DTOs) for video-tool.

All models are Pydantic BaseModel subclasses.
No I/O, no framework side-effects — pure data + validation only.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.exceptions import (
    ConflictingOutputModeError,
    InvalidIntervalError,
    InvalidSubfolderError,
    InvalidTimeFormatError,
)


class Quality(StrEnum):
    """Encoding quality preset for video and audio conversions."""

    ORIGINAL = "original"  # Direct stream copy without re-encoding (lossless)
    HIGH = "high"          # CRF 18 / 320 kbps audio — large file, best quality
    MEDIUM = "medium"      # CRF 24 / 192 kbps audio — balanced (default)
    LOW = "low"            # CRF 30 / 128 kbps audio — small file, lower quality

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


# Accepts: SS  |  MM:SS or MM.SS  |  HH:MM:SS or HH.MM.SS
_TIME_PATTERN = re.compile(r"^\d+(?:[:.\.]\d+){0,2}$")

# Characters illegal in a single Windows/POSIX path segment.
_ILLEGAL_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def parse_time_to_seconds(value: str) -> float:
    """Convert a time string to total seconds.

    Accepted formats (`:` and `.` are interchangeable as separators):
        SS            – plain seconds (e.g. ``90``)
        MM:SS         – minutes and seconds (e.g. ``1:30`` or ``1.30``)
        HH:MM:SS      – hours, minutes, seconds (e.g. ``1:01:30``)

    Raises:
        InvalidTimeFormatError: if the format is not recognised.
    """
    stripped = value.strip()
    if not _TIME_PATTERN.match(stripped):
        raise InvalidTimeFormatError(value)
    parts = re.split(r"[:.]", stripped)
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        mins, secs = int(parts[0]), float(parts[1])
        if secs >= 60:
            raise InvalidTimeFormatError(value)
        return mins * 60 + secs
    if len(parts) == 3:
        hrs, mins, secs = int(parts[0]), int(parts[1]), float(parts[2])
        if mins >= 60 or secs >= 60:
            raise InvalidTimeFormatError(value)
        return hrs * 3600 + mins * 60 + secs
    raise InvalidTimeFormatError(value)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    """Application configuration loaded from environment variables."""

    source: Path
    target: Path

    @field_validator("source")
    @classmethod
    def source_must_exist(cls, v: Path) -> Path:
        if not v.exists() or not v.is_dir():
            from domain.exceptions import SourceFolderNotFoundError
            raise SourceFolderNotFoundError(str(v))
        return v

    @field_validator("target")
    @classmethod
    def target_must_exist(cls, v: Path) -> Path:
        if not v.exists() or not v.is_dir():
            from domain.exceptions import TargetFolderNotFoundError
            raise TargetFolderNotFoundError(str(v))
        return v


class VideoFile(BaseModel):
    """Represents a discovered video file in the SOURCE folder."""

    name: str        # filename without extension
    extension: str   # e.g. ".mp4"
    path: Path       # absolute path to the file

    @property
    def display_name(self) -> str:
        return f"{self.name}{self.extension}"


class ClipInterval(BaseModel):
    """Represents a single user-defined clip request."""

    start: str = "00:00:00"  # defaults to beginning of video
    end: str | None = None   # None means end of video
    title: str               # user-provided name for the clip
    audio_only: bool = False  # True → extract audio as MP3 instead of video
    quality: Quality = Quality.MEDIUM  # encoding quality preset
    subfolder: str | None = None  # optional single-level project subfolder under TARGET
    fade_in_seconds: float = Field(default=0.0, ge=0.0)   # fade in from black/silence
    fade_out_seconds: float = Field(default=0.0, ge=0.0)  # fade out to black/silence
    watermark_text: str | None = None  # optional text burned into the bottom-right corner
    burn_subtitles: bool = False  # True → burn in a sidecar <video_stem>.srt, if present
    as_gif: bool = False  # True → export as an animated GIF instead of a video/audio file

    @field_validator("subfolder", mode="before")
    @classmethod
    def validate_subfolder(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        if stripped in {".", ".."} or _ILLEGAL_PATH_CHARS.search(stripped):
            raise InvalidSubfolderError(v)
        return stripped

    @field_validator("watermark_text", mode="before")
    @classmethod
    def validate_watermark_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @field_validator("start", mode="before")
    @classmethod
    def validate_start_format(cls, v: str) -> str:
        parse_time_to_seconds(v)  # raises InvalidTimeFormatError if invalid
        return v.strip()

    @field_validator("end", mode="before")
    @classmethod
    def validate_end_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        parse_time_to_seconds(v)  # raises InvalidTimeFormatError if invalid
        return v.strip()

    @model_validator(mode="after")
    def end_must_be_after_start(self) -> ClipInterval:
        if self.end is not None and parse_time_to_seconds(self.end) <= parse_time_to_seconds(self.start):
            raise InvalidIntervalError(self.start, self.end)
        return self

    @model_validator(mode="after")
    def audio_only_and_gif_are_mutually_exclusive(self) -> ClipInterval:
        if self.audio_only and self.as_gif:
            raise ConflictingOutputModeError()
        return self

    @property
    def start_seconds(self) -> float:
        return parse_time_to_seconds(self.start)

    @property
    def end_seconds(self) -> float | None:
        return parse_time_to_seconds(self.end) if self.end is not None else None


class ClipResult(BaseModel):
    """Represents the outcome of a single clip operation."""

    title: str
    output_path: Path
    success: bool
    error: str | None = None


class AudioResult(BaseModel):
    """Represents the outcome of an audio extraction operation."""

    title: str
    output_path: Path
    success: bool
    error: str | None = None


class JobStatus(StrEnum):
    """Lifecycle state of a ClipJob inside the processing queue."""

    PENDING = "pending"        # queued, waiting for the worker to pick it up
    PROCESSING = "processing"  # currently being cut/extracted
    DONE = "done"              # finished successfully
    ERROR = "error"            # finished with an error


class ClipJob(BaseModel):
    """A single clip request enqueued for background processing.

    Created the instant the user accepts a clip in the form, independently of
    which video is currently selected — several jobs for different videos can
    be queued and processed one after another (FIFO).
    """

    id: str
    video: VideoFile
    interval: ClipInterval
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0  # 0..1, only meaningful while PROCESSING
    result: ClipResult | AudioResult | None = None


class ClipPreset(BaseModel):
    """A named, reusable set of clip options (quality/audio/subfolder), not tied
    to a specific time interval or video."""

    quality: Quality = Quality.MEDIUM
    audio_only: bool = False
    subfolder: str | None = None


class UserPreferences(BaseModel):
    """User-level preferences persisted across app restarts (not env-derived)."""

    default_quality: Quality = Quality.MEDIUM
    last_source: Path | None = None
    last_target: Path | None = None
    presets: dict[str, ClipPreset] = Field(default_factory=dict)
