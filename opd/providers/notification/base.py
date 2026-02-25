"""Base class for notification providers."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import Provider


class NotificationProvider(Provider):
    """Base class for all notification providers.

    Subclasses must implement `send()` to deliver a notification
    through their specific channel (inbox, feishu, etc.).
    """

    @abstractmethod
    async def send(self, title: str, content: str, link: str = "") -> bool:
        """Send a notification. Returns True on success."""
