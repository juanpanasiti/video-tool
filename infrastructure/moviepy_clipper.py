"""Concrete implementation of IClipper using moviepy v2."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from proglog import ProgressBarLogger

from application.ports import IClipper
from domain.exceptions import ClipProcessingError
from domain.models import ClipInterval, ClipResult, Quality, VideoFile
from infrastructure.filename_utils import escape_ffmpeg_filter_path, sanitize_filename

logger = logging.getLogger("video_tool.moviepy_clipper")


class _FrameLogger(ProgressBarLogger):
    """Bridges proglog frame-level callbacks to a simple ``(current, total)`` callable."""

    def __init__(self, on_progress: Callable[[float, float], None]) -> None:
        super().__init__()
        self._on_progress = on_progress
        self._totals: dict[str, float] = {}

    def bars_callback(self, bar: str, attr: str, value: float, old_value: float | None = None) -> None:
        if attr == "total":
            self._totals[bar] = float(value)
        elif attr == "index":
            total = self._totals.get(bar, 0.0)
            if total > 0:
                self._on_progress(float(value), total)


class MoviePyClipper(IClipper):
    """Cuts video clips using moviepy v2."""

    def cut(
        self,
        video: VideoFile,
        interval: ClipInterval,
        target: Path,
        on_progress: Callable[[float, float], None] | None = None,
    ) -> ClipResult:
        """Cut a subclip and write it to *target*.

        *on_progress* is called with ``(current, total)`` as frames are encoded.
        Output filename: ``<video.name> - <interval.title><video.extension>``
        """
        safe_title = sanitize_filename(interval.title)
        output_name = f"{video.name} - {safe_title}{video.extension}"
        output_path = target / output_name

        frame_logger = _FrameLogger(on_progress) if on_progress is not None else None

        # Decoder name → encoder name mapping for common codecs
        _CODEC_MAP: dict[str, str] = {
            "h264": "libx264",
            "hevc": "libx265",
            "vp9": "libvpx-vp9",
            "av1": "libaom-av1",
            "mpeg4": "mpeg4",
            "vp8": "libvpx",
        }

        try:
            from moviepy import VideoFileClip, afx, vfx

            with VideoFileClip(str(video.path)) as clip:
                if interval.start_seconds >= clip.duration:
                    raise ValueError(
                        f"Start time ({interval.start_seconds:.2f}s) should be smaller "
                        f"than clip's duration ({clip.duration:.2f}s)."
                    )
                if interval.end_seconds is not None and interval.end_seconds > clip.duration:
                    raise ValueError(
                        f"End time ({interval.end_seconds:.2f}s) should be smaller or equal "
                        f"to clip's duration ({clip.duration:.2f}s)."
                    )

                has_effects = bool(
                    interval.fade_in_seconds > 0
                    or interval.fade_out_seconds > 0
                    or interval.watermark_text
                    or (interval.burn_subtitles and video.path.with_suffix(".srt").exists())
                )

                if (
                    interval.quality == Quality.ORIGINAL
                    and not interval.audio_only
                    and not interval.as_gif
                    and not has_effects
                ):
                    import subprocess

                    import imageio_ffmpeg

                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    cmd: list[str] = [ffmpeg_exe, "-y"]
                    if interval.start_seconds > 0:
                        cmd.extend(["-ss", str(interval.start_seconds)])
                    if interval.end_seconds is not None:
                        cmd.extend(["-to", str(interval.end_seconds)])
                    cmd.extend([
                        "-i", str(video.path),
                        "-c", "copy",
                        "-avoid_negative_ts", "make_zero",
                        str(output_path),
                    ])
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                    if proc.returncode != 0:
                        raise RuntimeError(f"FFmpeg stream copy failed: {proc.stderr}")
                    if on_progress is not None:
                        on_progress(1.0, 1.0)
                    return ClipResult(
                        title=interval.title,
                        output_path=output_path,
                        success=True,
                    )

                infos = clip.reader.infos
                decoder_codec = infos.get("video_codec", "")
                codec = _CODEC_MAP.get(decoder_codec, "libx264")

                _CRF_BY_QUALITY: dict[Quality, str] = {
                    Quality.ORIGINAL: "18",
                    Quality.HIGH: "18",
                    Quality.MEDIUM: "24",
                    Quality.LOW: "30",
                }
                _AUDIO_BITRATE_BY_QUALITY: dict[Quality, str] = {
                    Quality.ORIGINAL: "320k",
                    Quality.HIGH: "320k",
                    Quality.MEDIUM: "192k",
                    Quality.LOW: "128k",
                }

                crf = _CRF_BY_QUALITY[interval.quality]
                audio_bitrate = _AUDIO_BITRATE_BY_QUALITY[interval.quality]

                # Use CRF-based encoding for consistent quality based on the selected preset.
                _CRF_MAP: dict[str, list[str]] = {
                    "libx264": ["-crf", crf],
                    "libx265": ["-x265-params", f"crf={crf}"],
                    "libvpx": ["-crf", crf, "-b:v", "0"],
                    "libvpx-vp9": ["-crf", crf, "-b:v", "0"],
                    "libaom-av1": ["-crf", crf, "-b:v", "0"],
                }
                ffmpeg_params: list[str] | None = _CRF_MAP.get(codec)

                subclip = clip.subclipped(interval.start_seconds, interval.end_seconds)

                fade_in = interval.fade_in_seconds
                fade_out = interval.fade_out_seconds

                if interval.audio_only:
                    output_path = output_path.with_suffix(".mp3")
                    audio = subclip.audio
                    audio_effects = []
                    if fade_in > 0:
                        audio_effects.append(afx.AudioFadeIn(fade_in))
                    if fade_out > 0:
                        audio_effects.append(afx.AudioFadeOut(fade_out))
                    if audio_effects:
                        audio = audio.with_effects(audio_effects)
                    audio.write_audiofile(
                        str(output_path),
                        codec="libmp3lame",
                        bitrate=audio_bitrate,
                        logger=None,
                    )
                else:
                    video_effects = []
                    if fade_in > 0:
                        video_effects.append(vfx.FadeIn(fade_in))
                    if fade_out > 0:
                        video_effects.append(vfx.FadeOut(fade_out))
                    if video_effects:
                        subclip = subclip.with_effects(video_effects)
                        if subclip.audio is not None:
                            audio_effects = []
                            if fade_in > 0:
                                audio_effects.append(afx.AudioFadeIn(fade_in))
                            if fade_out > 0:
                                audio_effects.append(afx.AudioFadeOut(fade_out))
                            subclip = subclip.with_audio(subclip.audio.with_effects(audio_effects))

                    if interval.watermark_text:
                        from moviepy import CompositeVideoClip, TextClip

                        text_clip = (
                            TextClip(
                                text=interval.watermark_text,
                                font_size=max(14, subclip.h // 20),
                                color="white",
                                stroke_color="black",
                                stroke_width=1,
                            )
                            .with_duration(subclip.duration)
                            .with_position(("right", "bottom"))
                        )
                        subclip = CompositeVideoClip([subclip, text_clip]).with_audio(subclip.audio)

                    if interval.as_gif:
                        output_path = output_path.with_suffix(".gif")
                        subclip.write_gif(str(output_path), fps=clip.fps, logger=None)
                    else:
                        tmp_srt_path: Path | None = None
                        if interval.burn_subtitles:
                            srt_path = video.path.with_suffix(".srt")
                            if srt_path.exists():
                                from infrastructure.srt_utils import shift_srt

                                shifted = shift_srt(
                                    srt_path.read_text(encoding="utf-8", errors="replace"),
                                    offset_seconds=interval.start_seconds,
                                    duration_seconds=subclip.duration,
                                )
                                if shifted.strip():
                                    tmp_srt_path = output_path.with_name(output_path.name + ".tmp.srt")
                                    tmp_srt_path.write_text(shifted, encoding="utf-8")
                                    escaped = escape_ffmpeg_filter_path(str(tmp_srt_path))
                                    ffmpeg_params = [
                                        *(ffmpeg_params or []), "-vf", f"subtitles='{escaped}'"
                                    ]
                            else:
                                logger.debug(
                                    "burn_subtitles requested but no sidecar .srt found for %s",
                                    video.path,
                                )

                        try:
                            subclip.write_videofile(
                                str(output_path),
                                fps=clip.fps,
                                codec=codec,
                                audio_bitrate=audio_bitrate,
                                ffmpeg_params=ffmpeg_params,
                                logger=frame_logger,
                            )
                        finally:
                            if tmp_srt_path is not None:
                                tmp_srt_path.unlink(missing_ok=True)

        except Exception as exc:
            logger.exception("Failed to cut clip '%s' from %s", interval.title, video.path)
            return ClipResult(
                title=interval.title,
                output_path=output_path,
                success=False,
                error=str(ClipProcessingError(interval.title, str(exc))),
            )

        return ClipResult(
            title=interval.title,
            output_path=output_path,
            success=True,
        )
