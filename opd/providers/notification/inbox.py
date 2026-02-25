"""Inbox (站内信) notification provider — writes to DB."""

from __future__ import annotations

import logging

from opd.capabilities.base import HealthStatus
from opd.providers.notification.base import NotificationProvider

logger = logging.getLogger(__name__)


class InboxProvider(NotificationProvider):
    """Writes notifications to the Notification DB table.

    The actual DB write happens in the notify service layer which passes
    `session_factory`, `story_id`, and `project_id` via config at send time.
    This provider acts as a marker — the service layer handles persistence.
    """

    CONFIG_SCHEMA: list[dict] = []

    async def send(self, title: str, content: str, link: str = "") -> bool:
        """Inbox send is handled by the notify service layer directly."""
        # The notify service writes the Notification record itself
        # when it detects an inbox provider. This method is a no-op stub.
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, message="站内信始终可用")
