"""Story lifecycle API routes."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.db.models import (
    AIMessage,
    Clarification,
    Round,
    RoundStatus,
    RoundType,
    Story,
    StoryStatus,
)
from opd.engine.orchestrator import Orchestrator
from opd.models.schemas import AnswerRequest, CreateStoryRequest

router = APIRouter(prefix="/api", tags=["stories"])


@router.post("/projects/{project_id}/stories")
async def create_story(
    project_id: int, req: CreateStoryRequest, db: AsyncSession = Depends(get_db)
):
    story = Story(
        project_id=project_id,
        title=req.title,
        raw_input=req.raw_input,
        feature_tag=req.feature_tag,
        status=StoryStatus.preparing,
        current_round=1,
    )
    db.add(story)
    await db.flush()
    # Create initial round
    round_ = Round(
        story_id=story.id, round_number=1, type=RoundType.initial, status=RoundStatus.active
    )
    db.add(round_)
    await db.flush()
    return {"id": story.id, "status": story.status.value}


@router.get("/stories/{story_id}")
async def get_story(story_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Story)
        .where(Story.id == story_id)
        .options(
            selectinload(Story.tasks),
            selectinload(Story.rounds).selectinload(Round.pull_requests),
            selectinload(Story.clarifications),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404
    active_round = next((r for r in story.rounds if r.status == RoundStatus.active), None)
    return {
        "id": story.id,
        "title": story.title,
        "status": story.status.value,
        "feature_tag": story.feature_tag,
        "raw_input": story.raw_input,
        "prd": story.prd,
        "confirmed_prd": story.confirmed_prd,
        "technical_design": story.technical_design,
        "detailed_design": story.detailed_design,
        "current_round": story.current_round,
        "tasks": [
            {
                "id": t.id, "title": t.title, "description": t.description,
                "order": t.order, "depends_on": t.depends_on,
            }
            for t in sorted(story.tasks, key=lambda t: t.order)
        ],
        "rounds": [
            {
                "id": r.id, "round_number": r.round_number, "type": r.type.value,
                "status": r.status.value, "branch_name": r.branch_name,
                "pull_requests": [
                    {"pr_number": pr.pr_number, "pr_url": pr.pr_url, "status": pr.status.value}
                    for pr in r.pull_requests
                ],
            }
            for r in story.rounds
        ],
        "clarifications": [
            {"id": c.id, "question": c.question, "answer": c.answer}
            for c in story.clarifications
        ],
        "active_round_id": active_round.id if active_round else None,
    }


@router.post("/stories/{story_id}/confirm")
async def confirm_stage(
    story_id: int, db: AsyncSession = Depends(get_db), orch: Orchestrator = Depends(get_orch)
):
    """Confirm current stage output and advance to next stage."""
    result = await db.execute(
        select(Story)
        .where(Story.id == story_id)
        .options(selectinload(Story.rounds), selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404

    status = story.status.value if not isinstance(story.status, str) else story.status
    transitions = {
        "preparing": ("clarifying", "prd", "confirmed_prd"),
        "clarifying": ("planning", "confirmed_prd", None),
        "planning": ("designing", "technical_design", None),
        "designing": ("coding", "detailed_design", None),
        "verifying": ("done", None, None),
    }
    if status not in transitions:
        return {"error": f"Cannot confirm in status: {status}"}, 400

    next_status, _, _ = transitions[status]
    # For clarifying → planning, copy prd to confirmed_prd if not set
    if status == "clarifying" and not story.confirmed_prd:
        story.confirmed_prd = story.prd

    story.status = next_status
    return {"id": story.id, "status": next_status}


@router.post("/stories/{story_id}/reject")
async def reject_stage(story_id: int, db: AsyncSession = Depends(get_db)):
    """Reject current stage output, stay in same stage for regeneration."""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404
    return {"id": story.id, "status": story.status.value, "message": "Stage output rejected"}


@router.post("/stories/{story_id}/answer")
async def answer_questions(
    story_id: int, req: AnswerRequest, db: AsyncSession = Depends(get_db)
):
    """Answer clarification questions."""
    for qa in req.answers:
        clarification = Clarification(
            story_id=story_id, question=qa.question, answer=qa.answer
        )
        db.add(clarification)
    return {"message": "Answers recorded", "count": len(req.answers)}


@router.post("/stories/{story_id}/iterate")
async def iterate_story(story_id: int, db: AsyncSession = Depends(get_db)):
    """Iterate: go back to coding with same branch/PR."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.rounds))
    )
    story = result.scalar_one_or_none()
    if not story or story.status != StoryStatus.verifying:
        return {"error": "Can only iterate from verifying status"}, 400

    story.status = StoryStatus.coding
    return {"id": story.id, "status": "coding", "action": "iterate"}


@router.post("/stories/{story_id}/restart")
async def restart_story(story_id: int, db: AsyncSession = Depends(get_db)):
    """Restart: new round, new branch, close old PR."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.rounds))
    )
    story = result.scalar_one_or_none()
    if not story or story.status != StoryStatus.verifying:
        return {"error": "Can only restart from verifying status"}, 400

    # Close current round
    active_round = next((r for r in story.rounds if r.status == RoundStatus.active), None)
    if active_round:
        active_round.status = RoundStatus.closed

    # Create new round
    story.current_round += 1
    new_round = Round(
        story_id=story.id,
        round_number=story.current_round,
        type=RoundType.restart,
        status=RoundStatus.active,
    )
    db.add(new_round)
    story.status = StoryStatus.designing
    return {"id": story.id, "status": "designing", "action": "restart"}


@router.post("/stories/{story_id}/stop")
async def stop_story(story_id: int, orch: Orchestrator = Depends(get_orch)):
    """Emergency stop current AI task."""
    # Find active round and stop its task
    # For now, try to stop by story_id
    stopped = orch.stop_task(str(story_id))
    return {"stopped": stopped}


@router.get("/stories/{story_id}/stream")
async def stream_messages(story_id: int, db: AsyncSession = Depends(get_db),
                          orch: Orchestrator = Depends(get_orch)):
    """SSE endpoint: replay history then stream live AI messages."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.rounds))
    )
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404

    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None
    )
    if not active_round:
        return {"error": "No active round"}, 404

    round_id = str(active_round.id)

    async def event_generator():
        # 1. Replay historical messages
        msg_result = await db.execute(
            select(AIMessage)
            .where(AIMessage.round_id == active_round.id)
            .order_by(AIMessage.created_at)
        )
        for msg in msg_result.scalars().all():
            event = {"type": msg.role.value, "content": msg.content}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 2. Subscribe to live messages
        queue = orch.subscribe(round_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            orch.unsubscribe(round_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/stories/{story_id}/preflight")
async def preflight_check(story_id: int, db: AsyncSession = Depends(get_db),
                          orch: Orchestrator = Depends(get_orch)):
    """Check capability health for the next stage."""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404

    status = story.status.value if not isinstance(story.status, str) else story.status
    stage = orch._stages.get(status)
    if not stage:
        return {"capabilities": {}, "ok": True}

    preflight = await orch.capabilities.preflight(
        stage.required_capabilities, stage.optional_capabilities
    )
    return {"ok": preflight.ok, "errors": preflight.errors, "warnings": preflight.warnings}
