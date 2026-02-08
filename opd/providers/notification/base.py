"""Abstract base class for notification providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class NotificationProvider(Provider):
    """Interface for sending notifications to users.

    An *event* is a plain dict with at least:

    - ``type`` -- event type string (e.g. ``task_completed``)
    - ``message`` -- human-readable summary
    - ``data`` -- optional extra payload
    """

    @abstractmethod
    async def notify(self, user_id: str, event: dict[str, Any]) -> None:
        """Send a notification to a single user."""

    @abstractmethod
    async def notify_batch(
        self, user_ids: list[str], event: dict[str, Any]
    ) -> None:
        """Send the same notification to multiple users."""
