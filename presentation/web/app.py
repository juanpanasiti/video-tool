"""NiceGUI application entry point for video-tool.

Wires infrastructure into a shared AppState and starts the native UI window.
"""

from __future__ import annotations

import asyncio

from nicegui import app, ui

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
from application.use_cases.process_clip_job import ProcessClipJob
from domain.models import AppConfig, UserPreferences
from presentation.web.queue_worker import QueueWorker
from presentation.web.state import AppState

_state: AppState | None = None
_worker: QueueWorker | None = None


def get_state() -> AppState:
    """Return the process-wide shared state (single native window, single client)."""
    if _state is None:
        raise RuntimeError("AppState has not been initialised; call run() first.")
    return _state


def get_worker() -> QueueWorker:
    """Return the process-wide background clip processing queue worker."""
    if _worker is None:
        raise RuntimeError("QueueWorker has not been initialised; call run() first.")
    return _worker


def run(
    config: AppConfig,
    repository: IVideoRepository,
    clipper: IClipper,
    audio_extractor: IAudioExtractor,
    preferences_store: IPreferencesStore,
    notifier: INotifier,
    thumbnailer: IThumbnailer,
    video_metadata: IVideoMetadata,
    concatenator: IConcatenator,
    preferences: UserPreferences | None = None,
) -> None:
    """Wire dependencies and launch the NiceGUI native window."""
    global _state, _worker
    _state = AppState(
        config=config,
        repository=repository,
        clipper=clipper,
        audio_extractor=audio_extractor,
        preferences_store=preferences_store,
        notifier=notifier,
        thumbnailer=thumbnailer,
        video_metadata=video_metadata,
        concatenator=concatenator,
        preferences=preferences if preferences is not None else preferences_store.load(),
    )
    _worker = QueueWorker(_state, ProcessClipJob(clipper=clipper, extractor=audio_extractor))

    # Imported for its @ui.page route-registration side effect.
    from presentation.web.pages import main_page  # noqa: F401

    app.on_startup(lambda: asyncio.create_task(_worker.run_forever()))

    ui.run(
        title="Video Tool",
        native=True,
        window_size=(1100, 800),
        reload=False,
        dark=True,
    )

