"""Unit tests for workspace lock manager."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.db.models import Project, Story, StoryStatus
from opd.engine.workspace_lock import (
    WorkspaceLockError,
    acquire_workspace_lock,
    check_workspace_lock,
    release_workspace_lock,
)


@pytest.mark.asyncio
async def test_acquire_lock_success(db_session: AsyncSession):
    """Test successfully acquiring workspace lock."""
    # Create test project and story
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story = Story(
        project_id=project.id,
        title="Test Story",
        status=StoryStatus.preparing,
    )
    db_session.add(story)
    await db_session.flush()

    # Acquire lock
    await acquire_workspace_lock(db_session, project.id, story.id)

    # Verify lock is acquired
    await db_session.refresh(project)
    await db_session.refresh(story)
    assert project.locked_by_story_id == story.id
    assert project.locked_at is not None
    assert story.has_workspace_lock is True


@pytest.mark.asyncio
async def test_acquire_lock_conflict(db_session: AsyncSession):
    """Test lock conflict when workspace is already locked."""
    # Create test project and two stories
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story1 = Story(
        project_id=project.id,
        title="Story 1",
        status=StoryStatus.preparing,
    )
    story2 = Story(
        project_id=project.id,
        title="Story 2",
        status=StoryStatus.preparing,
    )
    db_session.add_all([story1, story2])
    await db_session.flush()

    # Story 1 acquires lock
    await acquire_workspace_lock(db_session, project.id, story1.id)

    # Story 2 tries to acquire lock - should fail
    with pytest.raises(WorkspaceLockError) as exc_info:
        await acquire_workspace_lock(db_session, project.id, story2.id)

    assert exc_info.value.locked_by_story_id == story1.id
    assert "locked by story" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_release_lock_success(db_session: AsyncSession):
    """Test successfully releasing workspace lock."""
    # Create test project and story
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story = Story(
        project_id=project.id,
        title="Test Story",
        status=StoryStatus.preparing,
    )
    db_session.add(story)
    await db_session.flush()

    # Acquire then release lock
    await acquire_workspace_lock(db_session, project.id, story.id)
    await release_workspace_lock(db_session, project.id, story.id)

    # Verify lock is released
    await db_session.refresh(project)
    await db_session.refresh(story)
    assert project.locked_by_story_id is None
    assert project.locked_at is None
    assert story.has_workspace_lock is False


@pytest.mark.asyncio
async def test_release_lock_by_non_owner(db_session: AsyncSession):
    """Test that non-owner cannot release lock."""
    # Create test project and two stories
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story1 = Story(
        project_id=project.id,
        title="Story 1",
        status=StoryStatus.preparing,
    )
    story2 = Story(
        project_id=project.id,
        title="Story 2",
        status=StoryStatus.preparing,
    )
    db_session.add_all([story1, story2])
    await db_session.flush()

    # Story 1 acquires lock
    await acquire_workspace_lock(db_session, project.id, story1.id)

    # Story 2 tries to release lock - should be no-op
    await release_workspace_lock(db_session, project.id, story2.id)

    # Verify lock is still held by story 1
    await db_session.refresh(project)
    assert project.locked_by_story_id == story1.id


@pytest.mark.asyncio
async def test_check_lock_status(db_session: AsyncSession):
    """Test checking workspace lock status."""
    # Create test project and story
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story = Story(
        project_id=project.id,
        title="Test Story",
        status=StoryStatus.preparing,
    )
    db_session.add(story)
    await db_session.flush()

    # Check unlocked status
    locked_by = await check_workspace_lock(db_session, project.id)
    assert locked_by is None

    # Acquire lock
    await acquire_workspace_lock(db_session, project.id, story.id)

    # Check locked status
    locked_by = await check_workspace_lock(db_session, project.id)
    assert locked_by == story.id


@pytest.mark.asyncio
async def test_acquire_lock_project_not_found(db_session: AsyncSession):
    """Test acquiring lock for non-existent project."""
    with pytest.raises(ValueError, match="Project .* not found"):
        await acquire_workspace_lock(db_session, 99999, 1)


@pytest.mark.asyncio
async def test_reacquire_same_lock(db_session: AsyncSession):
    """Test that same story can reacquire its own lock."""
    # Create test project and story
    project = Project(name="Test Project", repo_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.flush()

    story = Story(
        project_id=project.id,
        title="Test Story",
        status=StoryStatus.preparing,
    )
    db_session.add(story)
    await db_session.flush()

    # Acquire lock twice - should not raise error
    await acquire_workspace_lock(db_session, project.id, story.id)
    await acquire_workspace_lock(db_session, project.id, story.id)

    # Verify lock is still held
    await db_session.refresh(project)
    assert project.locked_by_story_id == story.id
