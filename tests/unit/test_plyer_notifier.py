"""Unit tests for infrastructure/plyer_notifier.py::PlyerNotifier."""

from __future__ import annotations

from pytest_mock import MockerFixture

from infrastructure.plyer_notifier import PlyerNotifier


def test_notify_calls_plyer_notification(mocker: MockerFixture) -> None:
    fake_notification = mocker.patch("plyer.notification")

    PlyerNotifier().notify("title", "message")

    fake_notification.notify.assert_called_once_with(
        title="title", message="message", app_name="Video Tool", timeout=5
    )


def test_notify_swallows_errors(mocker: MockerFixture) -> None:
    mocker.patch("plyer.notification.notify", side_effect=RuntimeError("no backend"))

    PlyerNotifier().notify("title", "message")  # must not raise
