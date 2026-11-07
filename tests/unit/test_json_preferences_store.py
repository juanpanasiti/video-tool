"""Unit tests for infrastructure/json_preferences_store.py::JsonPreferencesStore."""

from __future__ import annotations

from pathlib import Path

from domain.models import ClipPreset, Quality, UserPreferences
from infrastructure.json_preferences_store import JsonPreferencesStore


def test_load_returns_defaults_when_file_missing(tmp_path: Path) -> None:
    store = JsonPreferencesStore(tmp_path / "prefs.json")

    prefs = store.load()

    assert prefs == UserPreferences()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = JsonPreferencesStore(tmp_path / "nested" / "prefs.json")
    prefs = UserPreferences(
        default_quality=Quality.HIGH,
        last_source=tmp_path / "source",
        last_target=tmp_path / "target",
    )

    store.save(prefs)
    loaded = store.load()

    assert loaded == prefs


def test_load_returns_defaults_on_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "prefs.json"
    path.write_text("not json", encoding="utf-8")
    store = JsonPreferencesStore(path)

    assert store.load() == UserPreferences()


def test_presets_round_trip(tmp_path: Path) -> None:
    store = JsonPreferencesStore(tmp_path / "prefs.json")
    prefs = UserPreferences(
        presets={
            "reel": ClipPreset(quality=Quality.HIGH, audio_only=False, subfolder="reels"),
            "podcast-audio": ClipPreset(quality=Quality.LOW, audio_only=True),
        }
    )

    store.save(prefs)
    loaded = store.load()

    assert loaded.presets == prefs.presets

