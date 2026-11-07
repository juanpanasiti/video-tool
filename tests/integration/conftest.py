"""Shared fixtures for integration tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Write a tiny synthetic 2s video (with a sine-wave audio track) to a temp file.

    Real encode/decode via moviepy+ffmpeg, kept small (low fps/resolution/duration)
    so the integration test suite stays fast.
    """
    from moviepy import AudioClip, ColorClip

    duration = 2.0
    fps = 5

    video = ColorClip(size=(64, 48), color=(0, 128, 255), duration=duration)
    audio = AudioClip(
        frame_function=lambda t: np.sin(2 * np.pi * 440 * t),
        duration=duration,
        fps=22050,
    )
    clip = video.with_audio(audio)

    output = tmp_path / "sample.mp4"
    clip.write_videofile(str(output), fps=fps, codec="libx264", logger=None, audio_codec="aac")
    clip.close()

    return output
