"""Web notification provider."""

from __future__ import annotations

import logging

from opd.capabilities.base import HealthStatus

from .base import NotificationProvider

logger = logging.getLogger(__name__)


class WebNotificationProvider(NotificationProvider):
    """Logs notifications via Python logging."""

    async def notify(self, event: dict) -> None:
        logger.info("Notification: %s", event)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, message="Web notifications active")
