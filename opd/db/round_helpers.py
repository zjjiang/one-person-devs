"""Helper functions for managing rounds and active_round_id."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from opd.db.models import Round, Story


async def set_active_round(db: AsyncSession, story: Story, round: Round) -> None:
    """Set the active round for a story.

    Updates both the story.active_round_id field and the round.status.
    """
    story.active_round_id = round.id
    await db.flush()


async def clear_active_round(db: AsyncSession, story: Story) -> None:
    """Clear the active round for a story.

    Sets story.active_round_id to None.
    """
    story.active_round_id = None
    await db.flush()


async def close_active_round(
    db: AsyncSession, story: Story, close_reason: str | None = None
) -> Round | None:
    """Close the current active round and clear active_round_id.

    Returns the closed round if one existed, None otherwise.
    """
    if not story.active_round_id:
        return None

    # Update round status
    from opd.db.models import Round, RoundStatus
    await db.execute(
        update(Round)
        .where(Round.id == story.active_round_id)
        .values(status=RoundStatus.closed, close_reason=close_reason)
    )

    # Get the round before clearing
    closed_round = story.active_round

    # Clear active_round_id
    story.active_round_id = None
    await db.flush()

    return closed_round
