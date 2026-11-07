"""Concrete implementation of INotifier using plyer for cross-platform OS toasts."""

from __future__ import annotations

import logging

from application.ports import INotifier

logger = logging.getLogger("video_tool.plyer_notifier")


class PlyerNotifier(INotifier):
    """Shows a desktop notification via plyer. Never raises — logs and swallows errors.

    Some environments (headless CI, missing OS notification backend) don't support
    desktop notifications; this must not crash the job-processing pipeline.
    """

    def notify(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, app_name="Video Tool", timeout=5)
        except Exception as exc:
            logger.warning("Desktop notification failed: %s", exc)
