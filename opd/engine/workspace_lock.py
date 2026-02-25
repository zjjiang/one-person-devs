"""Workspace lock manager for multi-story concurrency control."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from opd.db.models import Project, Story


class WorkspaceLockError(Exception):
    """Workspace lock related error."""

    def __init__(self, message: str, locked_by_story_id: int | None = None):
        super().__init__(message)
        self.locked_by_story_id = locked_by_story_id


async def acquire_workspace_lock(
    db: AsyncSession,
    project_id: int,
    story_id: int,
) -> None:
    """
    Acquire workspace lock for a story.

    Args:
        db: Database session
        project_id: Project ID
        story_id: Story ID

    Raises:
        WorkspaceLockError: Workspace is already locked by another story
        ValueError: Project not found
    """
    from opd.db.models import Project, Story

    # Use SELECT FOR UPDATE to ensure atomicity
    stmt = select(Project).where(Project.id == project_id).with_for_update()
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Check if already locked by another story
    if project.locked_by_story_id and project.locked_by_story_id != story_id:
        raise WorkspaceLockError(
            f"Workspace is locked by story {project.locked_by_story_id}",
            locked_by_story_id=project.locked_by_story_id,
        )

    # Acquire lock
    project.locked_by_story_id = story_id
    project.locked_at = datetime.now(UTC)

    # Mark story as holding lock
    stmt = select(Story).where(Story.id == story_id)
    result = await db.execute(stmt)
    story = result.scalar_one_or_none()
    if story:
        story.has_workspace_lock = True

    # Note: Caller is responsible for committing the transaction


async def release_workspace_lock(
    db: AsyncSession,
    project_id: int,
    story_id: int,
) -> None:
    """
    Release workspace lock held by a story.

    Args:
        db: Database session
        project_id: Project ID
        story_id: Story ID (only the lock holder can release)
    """
    from opd.db.models import Project, Story

    stmt = select(Project).where(Project.id == project_id).with_for_update()
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        return

    # Only the lock holder can release
    if project.locked_by_story_id == story_id:
        project.locked_by_story_id = None
        project.locked_at = None

        # Clear story's lock holder flag
        stmt = select(Story).where(Story.id == story_id)
        result = await db.execute(stmt)
        story = result.scalar_one_or_none()
        if story:
            story.has_workspace_lock = False

        # Note: Caller is responsible for committing the transaction


async def check_workspace_lock(
    db: AsyncSession,
    project_id: int,
) -> int | None:
    """
    Check workspace lock status.

    Args:
        db: Database session
        project_id: Project ID

    Returns:
        Story ID holding the lock, or None if unlocked
    """
    from opd.db.models import Project

    stmt = select(Project.locked_by_story_id).where(Project.id == project_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

