"""Concrete implementation of IPreferencesStore backed by a JSON file on disk."""

from __future__ import annotations

import logging
from pathlib import Path

from application.ports import IPreferencesStore
from domain.models import UserPreferences

logger = logging.getLogger("video_tool.json_preferences_store")

DEFAULT_PREFERENCES_PATH = Path.home() / ".video-tool" / "preferences.json"


class JsonPreferencesStore(IPreferencesStore):
    """Reads/writes UserPreferences as JSON at *path* (default: user home dir)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_PREFERENCES_PATH

    def load(self) -> UserPreferences:
        """Return stored preferences, or defaults if the file is missing/corrupt."""
        if not self._path.exists():
            return UserPreferences()
        try:
            return UserPreferences.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to load preferences from %s: %s", self._path, exc)
            return UserPreferences()

    def save(self, preferences: UserPreferences) -> None:
        """Persist *preferences* as JSON, creating the parent directory if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(preferences.model_dump_json(indent=2), encoding="utf-8")
