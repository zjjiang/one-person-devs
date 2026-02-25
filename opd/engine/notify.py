"""Notification service — fan-out to all enabled notification providers."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import (
    GlobalCapabilityConfig,
    Notification,
    NotificationType,
    ProjectCapabilityConfig,
)

logger = logging.getLogger(__name__)


async def send_notification(
    session_factory: async_sessionmaker,
    event_type: NotificationType,
    title: str,
    message: str,
    link: str,
    registry: CapabilityRegistry,
    *,
    story_id: int | None = None,
    project_id: int | None = None,
    doc_content: str | None = None,
    doc_filename: str | None = None,
) -> None:
    """Send a notification to all enabled notification providers.

    1. Check if the project has notification capability enabled.
    2. Write a Notification record to DB (inbox) if inbox is among enabled providers.
    3. Fan-out to external providers (feishu, etc.) based on global config.
    Failures are logged but never raised.
    """
    try:
        async with session_factory() as db:
            async with db.begin():
                # Check project-level notification capability
                if project_id:
                    result = await db.execute(
                        select(ProjectCapabilityConfig).where(
                            ProjectCapabilityConfig.project_id == project_id,
                            ProjectCapabilityConfig.capability == "notification",
                            ProjectCapabilityConfig.enabled.is_(True),
                        )
                    )
                    if not result.scalars().first():
                        logger.debug(
                            "Project %s has no notification capability enabled, skipping",
                            project_id,
                        )
                        return

                # Inbox — write DB record
                db.add(Notification(
                    story_id=story_id,
                    project_id=project_id,
                    type=event_type,
                    title=title,
                    message=message,
                    link=link,
                ))

                # Fan-out to external providers (feishu, etc.)
                result = await db.execute(
                    select(GlobalCapabilityConfig).where(
                        GlobalCapabilityConfig.capability == "notification",
                        GlobalCapabilityConfig.enabled.is_(True),
                        GlobalCapabilityConfig.provider != "inbox",
                    )
                )
                rows = result.scalars().all()

                for row in rows:
                    try:
                        prov = registry.create_temp_provider(
                            "notification", row.provider, row.config or {},
                        )
                        if not prov:
                            logger.warning(
                                "Notification provider [%s] not found, skipping",
                                row.provider,
                            )
                            continue
                        await prov.initialize()
                        try:
                            if doc_content and doc_filename:
                                await prov.send_file(
                                    title, message, link,
                                    doc_content.encode("utf-8"), doc_filename,
                                )
                            else:
                                await prov.send(title, message, link)
                        finally:
                            await prov.cleanup()
                    except Exception:
                        logger.exception(
                            "Failed to send notification via [%s]", row.provider,
                        )
    except Exception:
        logger.exception("send_notification failed")
