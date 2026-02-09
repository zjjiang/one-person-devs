"""FastAPI router for Story lifecycle management."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_orchestrator, get_session
from opd.db.models import (
    AIMessage,
    Round,
    RoundStatus,
    Story,
    StoryStatus,
)
from opd.engine.orchestrator import (
    Orchestrator,
    OrchestratorError,
    StoryNotFoundError,
)
from opd.engine.state_machine import InvalidTransitionError
from opd.models.schemas import (
    AIMessageResponse,
    AnswerRequest,
    ConfirmPlanRequest,
    NewRoundRequest,
    RevisionRequest,
    RoundDetailResponse,
    RoundResponse,
    StoryCreate,
    StoryDetailResponse,
    StoryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stories"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _handle_engine_error(exc: Exception) -> HTTPException:
    """Convert engine exceptions to appropriate HTTP errors."""
    if isinstance(exc, StoryNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    if isinstance(exc, InvalidTransitionError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    if isinstance(exc, OrchestratorError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )


async def _get_story_or_404(
    db: AsyncSession, story_id: str
) -> Story:
    result = await db.execute(
        select(Story)
        .options(
            selectinload(Story.rounds)
            .selectinload(Round.clarifications),
        )
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if story is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {story_id} not found",
        )
    return story


# ---------------------------------------------------------------------------
# Story CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/api/projects/{project_id}/stories",
    response_model=StoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new story and start the first round",
)
async def create_story(
    project_id: str,
    body: StoryCreate,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Story:
    try:
        data = body.model_dump(exclude={"project_id"})
        story = await orch.create_story(db, project_id, data)
        return story
    except OrchestratorError as exc:
        raise _handle_engine_error(exc) from exc


@router.get(
    "/api/projects/{project_id}/stories",
    response_model=list[StoryResponse],
    summary="List stories for a project",
)
async def list_stories(
    project_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[Story]:
    result = await db.execute(
        select(Story)
        .where(Story.project_id == project_id)
        .order_by(Story.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/api/stories/{story_id}",
    response_model=StoryDetailResponse,
    summary="Get story detail with all rounds",
)
async def get_story(
    story_id: str,
    db: AsyncSession = Depends(get_session),
) -> Story:
    return await _get_story_or_404(db, story_id)


# ---------------------------------------------------------------------------
# Story actions
# ---------------------------------------------------------------------------

@router.post(
    "/api/stories/{story_id}/answer",
    response_model=RoundResponse,
    summary="Answer AI clarification questions",
)
async def answer_questions(
    story_id: str,
    body: AnswerRequest,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.answer_questions(db, story_id, body.answers)
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.get(
    "/api/stories/{story_id}/plan",
    response_model=list[AIMessageResponse],
    summary="Get the current plan (AI messages for the active round)",
)
async def get_plan(
    story_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[AIMessage]:
    story = await _get_story_or_404(db, story_id)
    if not story.rounds:
        return []
    active_round = max(story.rounds, key=lambda r: r.round_number)
    result = await db.execute(
        select(AIMessage)
        .where(AIMessage.round_id == active_round.id)
        .order_by(AIMessage.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/api/stories/{story_id}/generate-plan",
    response_model=RoundResponse,
    summary="Generate an implementation plan for the active round",
)
async def generate_plan(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.generate_plan(db, story_id)
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/confirm-plan",
    response_model=RoundResponse,
    summary="Confirm or reject the AI-generated plan",
)
async def confirm_plan(
    story_id: str,
    body: ConfirmPlanRequest,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.confirm_plan(
            db, story_id, body.confirmed, body.feedback
        )
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/revise",
    response_model=RoundResponse,
    summary="Trigger a revision pass",
)
async def revise(
    story_id: str,
    body: RevisionRequest,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.trigger_revision(
            db, story_id, body.mode, body.prompt
        )
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/new-round",
    response_model=RoundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new round for the story",
)
async def new_round(
    story_id: str,
    body: NewRoundRequest,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.new_round(
            db, story_id, body.type.value, new_requirement=body.requirement
        )
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/test",
    response_model=RoundResponse,
    summary="Trigger test execution",
)
async def trigger_test(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.trigger_test(db, story_id)
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/merge",
    response_model=StoryResponse,
    summary="Merge the PR and complete the story",
)
async def merge(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Story:
    try:
        story = await orch.merge(db, story_id)
        return story
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/stop",
    response_model=RoundResponse,
    summary="Emergency stop: cancel the running AI task and roll back",
)
async def stop_task(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.stop_task(db, story_id)
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/retry-pr",
    response_model=RoundResponse,
    summary="Retry commit/push/create PR after a failed attempt",
)
async def retry_pr(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Round:
    try:
        round_ = await orch.retry_pr(db, story_id)
        return round_
    except (OrchestratorError, InvalidTransitionError) as exc:
        raise _handle_engine_error(exc) from exc


@router.post(
    "/api/stories/{story_id}/reset",
    response_model=RoundResponse,
    summary="Reset the active round to a previous status (recovery)",
)
async def reset_round(
    story_id: str,
    body: dict,
    db: AsyncSession = Depends(get_session),
) -> Round:
    """Reset a stuck round back to a safe status."""
    target = body.get("target_status")
    allowed = {"planning", "reviewing", "pr_created"}
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_status must be one of {allowed}",
        )
    story = await _get_story_or_404(db, story_id)
    if not story.rounds:
        raise HTTPException(status_code=404, detail="No rounds")
    round_ = max(story.rounds, key=lambda r: r.round_number)
    round_.status = RoundStatus(target)
    await db.flush()
    await db.refresh(round_)
    return round_


@router.post(
    "/api/stories/{story_id}/close",
    response_model=StoryResponse,
    summary="Close/cancel a story",
)
async def close_story(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Story:
    story = await _get_story_or_404(db, story_id)
    if story.status == StoryStatus.cancelled:
        raise HTTPException(status_code=400, detail="Story is already closed")
    # Cancel any running background task
    if story.rounds:
        active_round = max(story.rounds, key=lambda r: r.round_number)
        task = orch._running_tasks.pop(active_round.id, None)
        if task and not task.done():
            task.cancel()
        if active_round.status.value != "done":
            active_round.status = RoundStatus.done
            active_round.close_reason = "Story closed"
    story.status = StoryStatus.cancelled
    await db.flush()
    await db.refresh(story)
    return story


@router.get(
    "/api/stories/{story_id}/task-status",
    summary="Check if a background AI task is running",
)
async def task_status(
    story_id: str,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> dict:
    story = await _get_story_or_404(db, story_id)
    if not story.rounds:
        return {"running": False, "status": "no_rounds"}
    active_round = max(story.rounds, key=lambda r: r.round_number)
    running = orch.is_task_running(active_round.id)
    return {
        "running": running,
        "status": active_round.status.value if hasattr(active_round.status, "value") else active_round.status,
        "round_id": active_round.id,
    }


@router.get(
    "/api/stories/{story_id}/logs",
    summary="Stream AI logs for the story (SSE)",
)
async def get_logs(
    story_id: str,
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Return AI messages as a Server-Sent Events stream.

    The client can consume this with an EventSource to get real-time
    updates on AI activity.
    """
    story = await _get_story_or_404(db, story_id)
    if not story.rounds:
        active_round_id = None
    else:
        active_round = max(story.rounds, key=lambda r: r.round_number)
        active_round_id = active_round.id

    async def event_stream() -> AsyncGenerator[str, None]:
        if active_round_id is None:
            yield "data: {\"type\": \"info\", \"message\": \"No rounds yet\"}\n\n"
            return

        result = await db.execute(
            select(AIMessage)
            .where(AIMessage.round_id == active_round_id)
            .order_by(AIMessage.created_at.asc())
        )
        messages = result.scalars().all()
        for msg in messages:
            import json
            payload = json.dumps({
                "id": msg.id,
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            })
            yield f"data: {payload}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
