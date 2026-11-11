"""Unit tests for configuration loading logic in main.py::load_config."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from domain.models import UserPreferences
from main import _parse_args, load_config


def _make_args(source: str | None = None, target: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(source=source, target=target)


def test_cli_args_take_highest_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_src = tmp_path / "cli_src"
    cli_tgt = tmp_path / "cli_tgt"
    cli_src.mkdir()

    env_src = tmp_path / "env_src"
    env_tgt = tmp_path / "env_tgt"
    env_src.mkdir()
    monkeypatch.setenv("SOURCE", str(env_src))
    monkeypatch.setenv("TARGET", str(env_tgt))

    pref_src = tmp_path / "pref_src"
    pref_tgt = tmp_path / "pref_tgt"
    pref_src.mkdir()
    prefs = UserPreferences(last_source=pref_src, last_target=pref_tgt)

    args = _make_args(source=str(cli_src), target=str(cli_tgt))
    config = load_config(args, preferences=prefs)

    assert config.source == cli_src.resolve()
    assert config.target == cli_tgt.resolve()


def test_env_vars_take_priority_over_preferences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_src = tmp_path / "env_src"
    env_tgt = tmp_path / "env_tgt"
    env_src.mkdir()
    monkeypatch.setenv("SOURCE", str(env_src))
    monkeypatch.setenv("TARGET", str(env_tgt))

    pref_src = tmp_path / "pref_src"
    pref_tgt = tmp_path / "pref_tgt"
    pref_src.mkdir()
    prefs = UserPreferences(last_source=pref_src, last_target=pref_tgt)

    args = _make_args()
    config = load_config(args, preferences=prefs)

    assert config.source == env_src.resolve()
    assert config.target == env_tgt.resolve()


def test_preferences_used_when_no_cli_or_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE", raising=False)
    monkeypatch.delenv("TARGET", raising=False)

    pref_src = tmp_path / "pref_src"
    pref_tgt = tmp_path / "pref_tgt"
    pref_src.mkdir()
    prefs = UserPreferences(last_source=pref_src, last_target=pref_tgt)

    args = _make_args()
    config = load_config(args, preferences=prefs)

    assert config.source == pref_src.resolve()
    assert config.target == pref_tgt.resolve()
    assert config.target.exists()


def test_preferences_missing_target_defaults_to_source_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE", raising=False)
    monkeypatch.delenv("TARGET", raising=False)

    pref_src = tmp_path / "pref_src"
    pref_src.mkdir()
    prefs = UserPreferences(last_source=pref_src, last_target=None)

    args = _make_args()
    config = load_config(args, preferences=prefs)

    assert config.source == pref_src.resolve()
    assert config.target == (pref_src / "output").resolve()
    assert config.target.exists()


def test_nonexistent_preference_source_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE", raising=False)
    monkeypatch.delenv("TARGET", raising=False)

    fake_src = tmp_path / "does_not_exist"
    prefs = UserPreferences(last_source=fake_src, last_target=tmp_path / "fake_tgt")

    args = _make_args()
    config = load_config(args, preferences=prefs)

    assert config.source == Path.cwd().resolve()
    assert config.target == (Path.cwd().resolve() / "output").resolve()


def test_parse_args_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["vtool"])
    args = _parse_args()
    assert args.source is None
    assert args.target is None
    assert args.browser is False


def test_parse_args_with_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["vtool", "/my/videos", "--target", "/my/clips", "--browser"])
    args = _parse_args()
    assert args.source == "/my/videos"
    assert args.target == "/my/clips"
    assert args.browser is True

