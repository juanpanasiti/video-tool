"""Unit tests for domain/models.py: time parsing and Pydantic validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.exceptions import (
    ConflictingOutputModeError,
    InvalidIntervalError,
    InvalidSubfolderError,
    InvalidTimeFormatError,
    SourceFolderNotFoundError,
    TargetFolderNotFoundError,
)
from domain.models import (
    AppConfig,
    ClipInterval,
    JobStatus,
    Quality,
    VideoFile,
    parse_time_to_seconds,
)


class TestParseTimeToSeconds:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("90", 90.0),
            ("1:30", 90.0),
            ("1.30", 90.0),
            ("0:00", 0.0),
            ("1:01:30", 3690.0),
            ("1.01.30", 3690.0),
        ],
    )
    def test_valid_formats(self, value: str, expected: float) -> None:
        assert parse_time_to_seconds(value) == expected

    @pytest.mark.parametrize("value", ["abc", "1:60", "1:99:00", "", "1:2:3:4"])
    def test_invalid_formats_raise(self, value: str) -> None:
        with pytest.raises(InvalidTimeFormatError):
            parse_time_to_seconds(value)


class TestClipInterval:
    def test_defaults(self) -> None:
        interval = ClipInterval(title="intro")
        assert interval.start == "00:00:00"
        assert interval.end is None
        assert interval.audio_only is False
        assert interval.quality == Quality.MEDIUM

    def test_end_after_start_is_valid(self) -> None:
        interval = ClipInterval(start="00:00:10", end="00:01:00", title="clip")
        assert interval.start_seconds == 10.0
        assert interval.end_seconds == 60.0

    def test_end_before_start_raises(self) -> None:
        with pytest.raises(InvalidIntervalError):
            ClipInterval(start="00:01:00", end="00:00:10", title="clip")

    def test_end_equal_start_raises(self) -> None:
        with pytest.raises(InvalidIntervalError):
            ClipInterval(start="00:00:10", end="00:00:10", title="clip")

    def test_invalid_start_format_raises(self) -> None:
        with pytest.raises(InvalidTimeFormatError):
            ClipInterval(start="not-a-time", title="clip")

    def test_subfolder_defaults_to_none(self) -> None:
        assert ClipInterval(title="clip").subfolder is None

    def test_subfolder_is_stripped(self) -> None:
        assert ClipInterval(title="clip", subfolder="  project-x  ").subfolder == "project-x"

    def test_blank_subfolder_becomes_none(self) -> None:
        assert ClipInterval(title="clip", subfolder="   ").subfolder is None

    def test_fade_defaults_to_zero(self) -> None:
        interval = ClipInterval(title="clip")
        assert interval.fade_in_seconds == 0.0
        assert interval.fade_out_seconds == 0.0

    def test_negative_fade_in_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClipInterval(title="clip", fade_in_seconds=-1.0)

    def test_negative_fade_out_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClipInterval(title="clip", fade_out_seconds=-1.0)

    def test_watermark_text_defaults_to_none(self) -> None:
        assert ClipInterval(title="clip").watermark_text is None

    def test_watermark_text_is_stripped(self) -> None:
        assert ClipInterval(title="clip", watermark_text="  © Me  ").watermark_text == "© Me"

    def test_blank_watermark_text_becomes_none(self) -> None:
        assert ClipInterval(title="clip", watermark_text="   ").watermark_text is None

    def test_as_gif_defaults_to_false(self) -> None:
        assert ClipInterval(title="clip").as_gif is False

    def test_audio_only_and_gif_together_raises(self) -> None:
        with pytest.raises(ConflictingOutputModeError):
            ClipInterval(title="clip", audio_only=True, as_gif=True)

    @pytest.mark.parametrize("value", ["..", "a/b", "a\\b", "a:b", "a*b"])
    def test_invalid_subfolder_raises(self, value: str) -> None:
        with pytest.raises(InvalidSubfolderError):
            ClipInterval(title="clip", subfolder=value)


class TestVideoFile:
    def test_display_name(self) -> None:
        video = VideoFile(name="movie", extension=".mp4", path=Path("/tmp/movie.mp4"))
        assert video.display_name == "movie.mp4"


class TestAppConfig:
    def test_valid_existing_dirs(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        config = AppConfig(source=source, target=target)

        assert config.source == source
        assert config.target == target

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()

        with pytest.raises(SourceFolderNotFoundError):
            AppConfig(source=tmp_path / "missing", target=target)

    def test_missing_target_raises(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()

        with pytest.raises(TargetFolderNotFoundError):
            AppConfig(source=source, target=tmp_path / "missing")


def test_job_status_values() -> None:
    assert JobStatus.PENDING == "pending"
    assert JobStatus.DONE == "done"


def test_quality_values() -> None:
    assert Quality.ORIGINAL == "original"
    assert Quality.HIGH == "high"
    assert Quality.MEDIUM == "medium"
    assert Quality.LOW == "low"
