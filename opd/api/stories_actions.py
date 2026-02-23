"""Story state-transition action routes: rollback, iterate, restart, stop."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.api.stories_tasks import _start_ai_stage
from opd.db.models import (
    AIMessage,
    Round,
    RoundStatus,
    RoundType,
    Story,
    StoryStatus,
)
from opd.engine.orchestrator import Orchestrator
from opd.engine.workspace import delete_doc, discard_branch
from opd.models.schemas import IterateRequest, RollbackRequest

logger = logging.getLogger(__name__)

actions_router = APIRouter(prefix="/api", tags=["stories"])

# Fields/files to clear when rolling back to a given stage.
# With input-hash change detection, we preserve downstream docs so that
# confirm_stage can skip AI when the input hasn't changed.
_ROLLBACK_CLEAR: dict[str, dict] = {
    "preparing": {
        "db_fields": ["confirmed_prd"],
        "doc_files": [],
    },
    "clarifying": {
        "db_fields": [],
        "doc_files": [],
    },
    "planning": {
        "db_fields": [],
        "doc_files": [],
    },
    "designing": {
        "db_fields": [],
        "doc_files": [],
    },
}


@actions_router.post("/stories/{story_id}/rollback")
async def rollback_story(
    story_id: int, req: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Roll back to a previous document stage and re-run AI."""
    result = await db.execute(
        select(Story)
        .where(Story.id == story_id)
        .options(
            selectinload(Story.project),
            selectinload(Story.tasks),
            selectinload(Story.rounds),
            selectinload(Story.clarifications),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    target = req.target_stage
    current = story.status.value if not isinstance(story.status, str) else story.status
    doc_stages = ["preparing", "clarifying", "planning", "designing"]
    if target not in doc_stages:
        raise HTTPException(status_code=400, detail=f"Invalid target stage: {target}")
    if doc_stages.index(target) >= doc_stages.index(current):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rollback from {current} to {target} (must be earlier stage)",
        )

    # Stop running AI tasks for this story
    orch.stop_task(str(story_id))
    orch.stop_task(f"chat_{story_id}")

    # Clear downstream outputs
    clear = _ROLLBACK_CLEAR.get(target, {})
    for field in clear.get("db_fields", []):
        setattr(story, field, None)
    for filename in clear.get("doc_files", []):
        delete_doc(story.project, story, filename)

    # Clear tasks when rolling back to any stage before designing
    if target in ("preparing", "clarifying", "planning"):
        for task in list(story.tasks):
            await db.delete(task)

    # Clear clarifications when rolling back to preparing
    if target == "preparing":
        for c in list(story.clarifications):
            await db.delete(c)

    # Clear chat messages for the active round
    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None,
    )
    if active_round:
        msg_result = await db.execute(
            select(AIMessage).where(AIMessage.round_id == active_round.id)
        )
        for msg in msg_result.scalars().all():
            await db.delete(msg)

    story.status = target
    await db.flush()

    return {"id": story.id, "status": target}


@actions_router.post("/stories/{story_id}/iterate")
async def iterate_story(story_id: int, req: IterateRequest | None = None,
                        db: AsyncSession = Depends(get_db),
                        orch: Orchestrator = Depends(get_orch)):
    """Iterate: close current round with feedback, create iterate round, re-code."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(
            selectinload(Story.rounds), selectinload(Story.project),
        )
    )
    story = result.scalar_one_or_none()
    if not story or story.status not in (StoryStatus.verifying, StoryStatus.coding):
        raise HTTPException(
            status_code=400, detail="Can only iterate from verifying/coding status"
        )

    orch.stop_task(str(story_id))
    feedback = req.feedback if req else ""

    # Close current round with feedback
    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None,
    )
    old_branch = active_round.branch_name if active_round else ""
    if active_round:
        active_round.status = RoundStatus.closed
        active_round.close_reason = feedback or None

    # Create new iterate round — inherit branch (continue on same branch)
    story.current_round += 1
    new_round = Round(
        story_id=story.id,
        round_number=story.current_round,
        type=RoundType.iterate,
        status=RoundStatus.active,
        branch_name=old_branch,
    )
    db.add(new_round)

    story.status = StoryStatus.coding
    story.coding_report = None
    story.test_guide = None
    story.coding_input_hash = None
    delete_doc(story.project, story, "coding_report.md")
    delete_doc(story.project, story, "test_guide.md")
    await db.flush()
    _start_ai_stage(story.id, orch)
    return {"id": story.id, "status": "coding", "action": "iterate"}


@actions_router.post("/stories/{story_id}/restart")
async def restart_story(story_id: int, req: IterateRequest | None = None,
                        db: AsyncSession = Depends(get_db),
                        orch: Orchestrator = Depends(get_orch)):
    """Restart: new round, new branch, close old PR."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(
            selectinload(Story.rounds), selectinload(Story.project),
        )
    )
    story = result.scalar_one_or_none()
    if not story or story.status not in (StoryStatus.verifying, StoryStatus.coding):
        raise HTTPException(
            status_code=400, detail="Can only restart from verifying/coding status"
        )

    orch.stop_task(str(story_id))
    feedback = req.feedback if req else ""

    # Close current round
    active_round = next((r for r in story.rounds if r.status == RoundStatus.active), None)
    old_branch = active_round.branch_name if active_round else ""
    if active_round:
        active_round.status = RoundStatus.closed
        active_round.close_reason = feedback or None

    # Discard old coding branch
    if old_branch:
        try:
            await discard_branch(story.project, old_branch)
        except Exception:
            logger.warning("Failed to discard branch %s", old_branch, exc_info=True)

    # Create new round (no branch — goes back to designing)
    story.current_round += 1
    new_round = Round(
        story_id=story.id,
        round_number=story.current_round,
        type=RoundType.restart,
        status=RoundStatus.active,
    )
    db.add(new_round)
    story.status = StoryStatus.designing
    story.coding_report = None
    story.test_guide = None
    story.coding_input_hash = None
    delete_doc(story.project, story, "coding_report.md")
    delete_doc(story.project, story, "test_guide.md")
    await db.flush()
    return {"id": story.id, "status": "designing", "action": "restart"}


@actions_router.post("/stories/{story_id}/stop")
async def stop_story(story_id: int, orch: Orchestrator = Depends(get_orch)):
    """Emergency stop current AI task."""
    stopped = orch.stop_task(str(story_id))
    return {"stopped": stopped}
