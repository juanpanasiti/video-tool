"""Integration tests for infrastructure/moviepy_clipper.py (real ffmpeg encode/decode)."""

from __future__ import annotations

from pathlib import Path

from domain.models import ClipInterval, Quality
from infrastructure.moviepy_clipper import MoviePyClipper
from infrastructure.video_repository import VideoRepository


def test_cut_produces_valid_video_file(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="my clip")
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0
    assert result.output_path.name == "sample - my clip.mp4"


def test_cut_sanitizes_illegal_characters_in_title(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="a/b:c")
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.name == "sample - a_b_c.mp4"


def test_cut_reports_progress(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="clip")
    target = tmp_path / "out"
    target.mkdir()
    progress_calls: list[tuple[float, float]] = []

    result = MoviePyClipper().cut(
        video=video,
        interval=interval,
        target=target,
        on_progress=lambda current, total: progress_calls.append((current, total)),
    )

    assert result.success, result.error
    assert len(progress_calls) > 0


def test_cut_audio_only_produces_mp3(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="00:00:01", title="clip", audio_only=True)
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.suffix == ".mp3"
    assert result.output_path.exists()


def test_cut_invalid_interval_beyond_duration_reports_failure(
    sample_video: Path, tmp_path: Path
) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    # The sample video is 2s long; requesting a clip starting after it ends should fail cleanly.
    interval = ClipInterval(start="00:00:05", end="00:00:06", title="clip")
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success is False


def test_cut_with_fade_in_and_out_produces_valid_video(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(
        start="00:00:00", end="1", title="faded", fade_in_seconds=0.2, fade_out_seconds=0.2
    )
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0


def test_cut_audio_only_with_fade_produces_valid_mp3(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(
        start="00:00:00",
        end="1",
        title="faded-audio",
        audio_only=True,
        fade_in_seconds=0.2,
        fade_out_seconds=0.2,
    )
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.suffix == ".mp3"
    assert result.output_path.exists()


def test_cut_with_watermark_text_produces_valid_video(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="1", title="watermarked", watermark_text="© Test")
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0


def test_cut_with_burn_subtitles_produces_valid_video(sample_video: Path, tmp_path: Path) -> None:
    srt_path = sample_video.with_suffix(".srt")
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8"
    )
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="1", title="subtitled", burn_subtitles=True)
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0
    # the temp shifted .srt must be cleaned up, not left next to the output
    assert not any(p.suffix == ".srt" for p in target.iterdir())


def test_cut_with_burn_subtitles_no_sidecar_still_succeeds(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="1", title="no-subs", burn_subtitles=True)
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error


def test_cut_as_gif_produces_valid_gif_file(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    interval = ClipInterval(start="00:00:00", end="1", title="animated", as_gif=True)
    target = tmp_path / "out"
    target.mkdir()

    result = MoviePyClipper().cut(video=video, interval=interval, target=target)

    assert result.success, result.error
    assert result.output_path.suffix == ".gif"
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0


def test_cut_respects_quality_presets(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    target = tmp_path / "out"
    target.mkdir()

    res_high = MoviePyClipper().cut(
        video=video,
        interval=ClipInterval(start="00:00:00", end="1", title="high", quality=Quality.HIGH),
        target=target,
    )
    res_low = MoviePyClipper().cut(
        video=video,
        interval=ClipInterval(start="00:00:00", end="1", title="low", quality=Quality.LOW),
        target=target,
    )

    assert res_high.success, res_high.error
    assert res_low.success, res_low.error
    assert res_high.output_path.stat().st_size > res_low.output_path.stat().st_size


def test_cut_original_quality_produces_valid_video(sample_video: Path, tmp_path: Path) -> None:
    video = VideoRepository().list_videos(sample_video.parent)[0]
    target = tmp_path / "out"
    target.mkdir()
    progress_called = False

    def on_progress(cur: float, tot: float) -> None:
        nonlocal progress_called
        progress_called = True

    result = MoviePyClipper().cut(
        video=video,
        interval=ClipInterval(start="00:00:00", end="00:00:01", title="orig", quality=Quality.ORIGINAL),
        target=target,
        on_progress=on_progress,
    )

    assert result.success, result.error
    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0
    assert progress_called
