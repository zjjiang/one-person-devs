"""Helper functions for stories_tasks.py to reduce function complexity."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from opd.db.models import Project, Round, Story
    from opd.engine.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


async def acquire_workspace_lock_for_coding(
    db: AsyncSession,
    story: Story,
    story_id: int,
    round_id: str,
    orch: Orchestrator,
) -> tuple[bool, str | None]:
    """Acquire workspace lock for coding stage.

    Returns:
        (success, error_message): If success is False, error_message contains the error.
    """
    from opd.engine.workspace_lock import WorkspaceLockError, acquire_workspace_lock

    try:
        await acquire_workspace_lock(db, story.project_id, story_id)
        logger.info(
            "Acquired workspace lock for story %s on project %s",
            story_id,
            story.project_id,
        )
        return True, None
    except WorkspaceLockError as e:
        # Lock conflict: query the locking story info
        locked_story_id = e.locked_by_story_id
        if locked_story_id:
            from opd.db.models import Story as StoryModel

            stmt = select(StoryModel).where(StoryModel.id == locked_story_id)
            result = await db.execute(stmt)
            locked_story = result.scalar_one_or_none()

            error_msg = (
                f"工作区被占用：Story #{locked_story_id} "
                f"'{locked_story.title if locked_story else 'Unknown'}' "
                f"正在使用该项目的工作区。请等待其完成或停止后再试。"
            )
        else:
            error_msg = "工作区被占用，请稍后再试。"

        logger.warning(
            "Workspace lock conflict for story %s: %s",
            story_id,
            error_msg,
        )
        # Publish error
        await orch.publish(round_id, {"type": "error", "content": error_msg})
        return False, error_msg


async def release_workspace_lock_for_coding(
    db: AsyncSession, project_id: int, story_id: int
) -> None:
    """Release workspace lock after coding stage completes/fails.

    Logs warning if release fails but doesn't raise exception.
    """
    from opd.engine.workspace_lock import release_workspace_lock

    try:
        await release_workspace_lock(db, project_id, story_id)
        logger.info("Released workspace lock for story %s", story_id)
    except Exception:
        logger.warning(
            "Failed to release workspace lock for story %s",
            story_id,
            exc_info=True,
        )


async def create_coding_branch_if_needed(
    active_round: Round,
    story: Story,
    orch: Orchestrator,
    session_factory,
) -> None:
    """Create coding branch if entering coding stage without one.

    Updates active_round.branch_name if successful.
    Logs warning if creation fails but doesn't raise exception.
    """
    if active_round.branch_name:
        return  # Branch already exists

    from opd.engine.workspace import create_coding_branch, generate_branch_name
    from sqlalchemy import update

    from opd.db.models import Round

    branch = generate_branch_name(story.id, active_round.round_number)
    lock = orch.get_workspace_lock(story.project_id)
    try:
        async with lock:
            await create_coding_branch(story.project, branch)
        active_round.branch_name = branch
        # Update in separate transaction to avoid lock conflicts
        async with session_factory() as db2:
            async with db2.begin():
                await db2.execute(
                    update(Round)
                    .where(Round.id == active_round.id)
                    .values(branch_name=branch)
                )
        logger.info("Created coding branch %s", branch)
    except Exception:
        logger.warning(
            "Branch creation failed, coding without branch",
            exc_info=True,
        )
