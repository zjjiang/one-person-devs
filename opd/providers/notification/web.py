"""Web notification provider with in-memory storage."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from opd.providers.notification.base import NotificationProvider

logger = logging.getLogger(__name__)


class WebNotificationProvider(NotificationProvider):
    """Stores notifications in an in-memory list.

    This is suitable for development and single-process deployments.
    For production use, notifications should be persisted to a database
    and delivered via WebSocket or SSE.

    Config keys:

    - ``max_per_user`` -- maximum notifications kept per user
      (default ``200``).  Oldest notifications are evicted when the
      limit is exceeded.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._max_per_user: int = int(config.get("max_per_user", 200))
        # user_id -> list of notification dicts
        self._store: dict[str, list[dict[str, Any]]] = {}

    async def notify(self, user_id: str, event: dict[str, Any]) -> None:
        notification = {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "type": event.get("type", "unknown"),
            "message": event.get("message", ""),
            "data": event.get("data"),
            "read": False,
            "created_at": time.time(),
        }
        user_list = self._store.setdefault(user_id, [])
        user_list.append(notification)
        # Evict oldest if over limit
        if len(user_list) > self._max_per_user:
            self._store[user_id] = user_list[-self._max_per_user :]
        logger.debug("Notification sent to user %s: %s", user_id, notification["type"])

    async def notify_batch(
        self, user_ids: list[str], event: dict[str, Any]
    ) -> None:
        for user_id in user_ids:
            await self.notify(user_id, event)

    # ------------------------------------------------------------------
    # Extra query helpers (not part of the ABC, but useful for the web UI)
    # ------------------------------------------------------------------

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return notifications for *user_id*, newest first."""
        items = self._store.get(user_id, [])
        if unread_only:
            items = [n for n in items if not n["read"]]
        # Return newest first, capped at limit
        return list(reversed(items[-limit:]))

    async def mark_read(self, user_id: str, notification_id: str) -> None:
        """Mark a single notification as read."""
        for n in self._store.get(user_id, []):
            if n["id"] == notification_id:
                n["read"] = True
                return
        raise KeyError(f"Notification not found: {notification_id}")

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications for *user_id* as read. Returns count."""
        count = 0
        for n in self._store.get(user_id, []):
            if not n["read"]:
                n["read"] = True
                count += 1
        return count
