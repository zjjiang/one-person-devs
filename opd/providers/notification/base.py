"""Notification provider base class."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import HealthStatus, Provider


class NotificationProvider(Provider):
    """Abstract base for notification providers."""

    @abstractmethod
    async def notify(self, event: dict) -> None:
        """Send a notification for the given event."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check if the notification provider is reachable."""
