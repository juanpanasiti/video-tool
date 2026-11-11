"""video-tool entry point.

Responsibilities:
- Load environment variables from .env (if present).
- Validate configuration via AppConfig (domain model).
- Wire all layers together (dependency injection).
- Launch the NiceGUI native UI.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from domain.exceptions import SourceFolderNotFoundError
from domain.models import AppConfig, UserPreferences
from infrastructure.json_preferences_store import JsonPreferencesStore
from infrastructure.logging_config import configure_logging
from infrastructure.moviepy_audio_extractor import MoviePyAudioExtractor
from infrastructure.moviepy_clipper import MoviePyClipper
from infrastructure.moviepy_concatenator import MoviePyConcatenator
from infrastructure.moviepy_thumbnailer import MoviePyThumbnailer
from infrastructure.moviepy_video_metadata import MoviePyVideoMetadata
from infrastructure.plyer_notifier import PlyerNotifier
from infrastructure.video_repository import VideoRepository
from presentation.web import app as web_app

logger = logging.getLogger("video_tool.main")


def _parse_args() -> argparse.Namespace:
    """Parse optional CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="vtool",
        description="Trim video files into named clips.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        metavar="SOURCE",
        help="Folder containing video files (default: current directory).",
    )
    parser.add_argument(
        "--target", "-t",
        metavar="TARGET",
        dest="target",
        help="Output folder for clips (default: <source>/output).",
    )
    return parser.parse_args()


def load_config(
    args: argparse.Namespace,
    preferences: UserPreferences | None = None,
) -> AppConfig:
    """Resolve and validate application configuration.

    Priority for each path: CLI argument > environment variable > preferences > built-in default.
    SOURCE defaults to the current working directory.
    TARGET defaults to <source>/output and is created automatically if absent.
    """
    load_dotenv()

    # Source resolution: CLI > ENV > preferences (if directory exists) > cwd
    source: Path
    using_pref_source = False
    if args.source:
        source = Path(args.source).resolve()
    elif env_source := os.getenv("SOURCE", "").strip():
        source = Path(env_source).resolve()
    elif preferences and preferences.last_source and preferences.last_source.is_dir():
        source = preferences.last_source.resolve()
        using_pref_source = True
    else:
        if preferences and preferences.last_source and not preferences.last_source.is_dir():
            logger.warning(
                "Configured last_source '%s' does not exist or is not a directory; falling back to cwd",
                preferences.last_source,
            )
        source = Path.cwd().resolve()

    # Target resolution: CLI > ENV > preferences (when source came from preferences) > <source>/output
    target: Path
    if args.target:
        target = Path(args.target).resolve()
    elif env_target := os.getenv("TARGET", "").strip():
        target = Path(env_target).resolve()
    elif using_pref_source and preferences and preferences.last_target:
        target = preferences.last_target.resolve()
    else:
        target = (source / "output").resolve()

    # Auto-create target so AppConfig validation passes and clips have somewhere to land.
    target.mkdir(parents=True, exist_ok=True)

    try:
        config = AppConfig(source=source, target=target)
    except SourceFolderNotFoundError as exc:
        logger.error("Configuration error: %s", exc)
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected configuration error")
        print(f"Unexpected configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    return config


def main() -> None:
    log_file = configure_logging()
    logger.info("Starting video-tool (log file: %s)", log_file)
    args = _parse_args()

    # Wire infrastructure
    preferences_store = JsonPreferencesStore()
    preferences = preferences_store.load()
    config = load_config(args, preferences=preferences)

    repository = VideoRepository()
    clipper = MoviePyClipper()
    audio_extractor = MoviePyAudioExtractor()
    notifier = PlyerNotifier()
    thumbnailer = MoviePyThumbnailer()
    video_metadata = MoviePyVideoMetadata()
    concatenator = MoviePyConcatenator()

    try:
        web_app.run(
            config=config,
            repository=repository,
            clipper=clipper,
            audio_extractor=audio_extractor,
            preferences_store=preferences_store,
            notifier=notifier,
            thumbnailer=thumbnailer,
            video_metadata=video_metadata,
            concatenator=concatenator,
            preferences=preferences,
        )
    except KeyboardInterrupt:
        # asyncio/uvicorn re-raise this on Ctrl+C after internally cancelling the
        # server task; the shutdown itself already completed, so exit quietly
        # instead of letting Python print the CancelledError/KeyboardInterrupt traceback.
        # Must be caught here (not in the __main__ guard below): the installed
        # `vtool` console-script entry point imports and calls main() directly,
        # never going through that guard.
        logger.info("Shutting down (KeyboardInterrupt)")
        sys.exit(0)


# NiceGUI's native mode spawns the window via multiprocessing; "__mp_main__" must
# also trigger main() so the child process re-import doesn't fall through silently.
if __name__ in {"__main__", "__mp_main__"}:
    main()
