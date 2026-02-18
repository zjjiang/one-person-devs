"""Story lifecycle API routes."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.db.models import (
    AIMessage,
    AIMessageRole,
    Clarification,
    Project,
    ProjectCapabilityConfig,
    Round,
    RoundStatus,
    RoundType,
    Story,
    StoryStatus,
)
from opd.db.session import get_session_factory
from opd.engine.context import (
    build_clarifying_chat_prompt,
    build_designing_chat_prompt,
    build_planning_chat_prompt,
    build_refine_prd_prompt,
    parse_refine_response,
)
from opd.engine.orchestrator import Orchestrator
from opd.engine.stages.base import StageContext
from opd.engine.workspace import delete_doc, list_docs, read_doc, write_doc
from opd.models.schemas import (
    AnswerRequest,
    ChatRequest,
    CreateStoryRequest,
    RollbackRequest,
    UpdateDocRequest,
    UpdatePrdRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stories"])

# Stage output field → (Story model field, doc filename)
_OUTPUT_FIELDS = {
    "prd": "prd.md",
    "technical_design": "technical_design.md",
    "detailed_design": "detailed_design.md",
}


def _save_clarifications(db: AsyncSession, story: Story, raw_text: str) -> None:
    """Parse AI-generated questions JSON and save as Clarification records."""
    import re as _re

    # Try to extract JSON array from the text (AI may wrap it in markdown code blocks)
    json_match = _re.search(r"\[.*\]", raw_text, _re.DOTALL)
    if not json_match:
        logger.warning("Could not find JSON array in clarification output for story %s", story.id)
        return
    try:
        questions = json.loads(json_match.group())
    except json.JSONDecodeError:
        logger.warning("Failed to parse clarification JSON for story %s", story.id)
        return
    for item in questions:
        q = item.get("question", "").strip()
        if q:
            db.add(Clarification(story_id=story.id, question=q))


def _start_ai_stage(story_id: int, orch: Orchestrator) -> None:
    """Launch AI stage execution as a background task."""

    async def _run() -> None:
        await asyncio.sleep(0.5)
        logger.info("Background AI task starting for story %s", story_id)
        session_factory = get_session_factory()
        try:
            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Story)
                        .where(Story.id == story_id)
                        .options(
                            selectinload(Story.project).selectinload(Project.rules),
                            selectinload(Story.rounds),
                            selectinload(Story.tasks),
                            selectinload(Story.clarifications),
                        )
                    )
                    story = result.scalar_one_or_none()
                    if not story:
                        logger.warning("Story %s not found in background task", story_id)
                        return

                    # Build project-level capability registry
                    cap_result = await db.execute(
                        select(ProjectCapabilityConfig)
                        .where(ProjectCapabilityConfig.project_id == story.project_id)
                    )
                    cap_configs = cap_result.scalars().all()
                    registry = orch.capabilities
                    if cap_configs:
                        overrides = [
                            {
                                "capability": c.capability,
                                "enabled": c.enabled,
                                "provider_override": c.provider_override,
                                "config_override": c.config_override,
                            }
                            for c in cap_configs
                        ]
                        registry = await orch.capabilities.with_project_overrides(
                            overrides
                        )

                    status = (
                        story.status.value
                        if not isinstance(story.status, str)
                        else story.status
                    )
                    stage = orch._stages.get(status)
                    if not stage:
                        logger.warning("No stage handler for status: %s", status)
                        return

                    active_round = next(
                        (r for r in story.rounds if r.status == RoundStatus.active),
                        None,
                    )
                    if not active_round:
                        logger.warning("No active round for story %s", story_id)
                        return

                    round_id = str(active_round.id)
                    logger.info(
                        "Executing stage [%s] for story %s round %s",
                        status, story_id, round_id,
                    )

                    async def publish(event: dict) -> None:
                        await orch._publish(round_id, event)
                        msg_type = event.get("type", "")
                        content = event.get("content", "")
                        if msg_type in ("assistant", "tool") and content:
                            db.add(AIMessage(
                                round_id=active_round.id,
                                role=AIMessageRole(msg_type),
                                content=content,
                            ))

                    ctx = StageContext(
                        story=story, project=story.project, round=active_round,
                        capabilities=registry, publish=publish,
                    )

                    done_event: dict | None = None
                    try:
                        stage_result = await stage.execute(ctx)
                        if stage_result.success:
                            for fld, filename in _OUTPUT_FIELDS.items():
                                if fld in stage_result.output:
                                    content = stage_result.output[fld]
                                    rel_path = write_doc(
                                        story.project, story, filename, content,
                                    )
                                    setattr(story, fld, rel_path)
                            # Parse clarification questions into DB records
                            if "questions" in stage_result.output:
                                _save_clarifications(
                                    db, story, stage_result.output["questions"],
                                )
                            logger.info("Stage [%s] completed for story %s",
                                        status, story_id)
                            done_event = {"type": "done"}
                        else:
                            error_msg = "; ".join(stage_result.errors)
                            logger.error("Stage [%s] failed: %s", status, error_msg)
                            done_event = {"type": "error", "content": error_msg}
                    except Exception as e:
                        logger.exception("AI stage exception for story %s", story_id)
                        done_event = {"type": "error", "content": str(e)}
                    finally:
                        orch._running_tasks.pop(round_id, None)
            # Transaction committed — now publish done/error so frontend reads fresh data
            if done_event:
                await orch._publish(round_id, done_event)
        except Exception:
            logger.exception("Background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch._running_tasks[str(story_id)] = task


def _start_chat_ai(story_id: int, user_message: str, orch: Orchestrator) -> None:
    """Launch AI chat refinement as a background task."""

    async def _run() -> None:
        await asyncio.sleep(0.2)
        logger.info("Chat AI task starting for story %s", story_id)
        session_factory = get_session_factory()
        try:
            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Story)
                        .where(Story.id == story_id)
                        .options(
                            selectinload(Story.project).selectinload(Project.rules),
                            selectinload(Story.rounds),
                            selectinload(Story.tasks),
                            selectinload(Story.clarifications),
                        )
                    )
                    story = result.scalar_one_or_none()
                    if not story:
                        return

                    active_round = next(
                        (r for r in story.rounds if r.status == RoundStatus.active), None,
                    )
                    if not active_round:
                        return

                    round_id = str(active_round.id)

                    # Load conversation history
                    msg_result = await db.execute(
                        select(AIMessage)
                        .where(
                            AIMessage.round_id == active_round.id,
                            AIMessage.role.in_([AIMessageRole.user, AIMessageRole.assistant]),
                        )
                        .order_by(AIMessage.created_at)
                    )
                    history = [
                        {"role": m.role.value, "content": m.content}
                        for m in msg_result.scalars().all()
                    ]

                    # Build project-level capability registry
                    cap_result = await db.execute(
                        select(ProjectCapabilityConfig)
                        .where(ProjectCapabilityConfig.project_id == story.project_id)
                    )
                    cap_configs = cap_result.scalars().all()
                    registry = orch.capabilities
                    if cap_configs:
                        overrides = [
                            {
                                "capability": c.capability,
                                "enabled": c.enabled,
                                "provider_override": c.provider_override,
                                "config_override": c.config_override,
                            }
                            for c in cap_configs
                        ]
                        registry = await orch.capabilities.with_project_overrides(overrides)

                    ai = registry.get("ai")
                    if not ai:
                        await orch._publish(
                            round_id, {"type": "error", "content": "AI capability not available"}
                        )
                        return

                    # Build prompt based on stage
                    status = (
                        story.status.value
                        if not isinstance(story.status, str)
                        else story.status
                    )
                    prompt_builders = {
                        "preparing": build_refine_prd_prompt,
                        "clarifying": build_clarifying_chat_prompt,
                        "planning": build_planning_chat_prompt,
                        "designing": build_designing_chat_prompt,
                    }
                    builder = prompt_builders.get(status, build_refine_prd_prompt)
                    system_prompt, user_prompt = builder(
                        story, story.project, history, user_message,
                    )

                    # Map stage → (doc filename, story field, event type)
                    doc_map = {
                        "preparing": ("prd.md", "prd", "doc_updated"),
                        "clarifying": ("prd.md", "prd", "doc_updated"),
                        "planning": ("technical_design.md", "technical_design", "doc_updated"),
                        "designing": ("detailed_design.md", "detailed_design", "doc_updated"),
                    }
                    doc_filename, doc_field, evt_type = doc_map.get(
                        status, ("prd.md", "prd", "doc_updated"),
                    )

                    collected: list[str] = []
                    post_commit_events: list[dict] = []
                    try:
                        # Collect full AI response silently (no streaming raw chunks)
                        async for msg in ai.provider.refine_prd(system_prompt, user_prompt):
                            if msg.get("type") == "assistant" and msg.get("content"):
                                collected.append(msg["content"])

                        full_text = "\n".join(collected)
                        discussion, updated_doc = parse_refine_response(full_text)

                        # Only publish the short discussion as assistant message
                        if discussion:
                            db.add(AIMessage(
                                round_id=active_round.id,
                                role=AIMessageRole.assistant,
                                content=discussion,
                            ))
                            post_commit_events.append({
                                "type": "assistant", "content": discussion,
                            })

                        if updated_doc:
                            rel_path = write_doc(
                                story.project, story, doc_filename, updated_doc,
                            )
                            setattr(story, doc_field, rel_path)
                            post_commit_events.append({
                                "type": evt_type,
                                "content": updated_doc,
                                "filename": doc_filename,
                            })

                        post_commit_events.append({"type": "done"})
                    except Exception as e:
                        logger.exception("Chat AI exception for story %s", story_id)
                        post_commit_events.append(
                            {"type": "error", "content": str(e)}
                        )
                    finally:
                        orch._running_tasks.pop(f"chat_{story_id}", None)
            # Transaction committed — publish final events
            for evt in post_commit_events:
                await orch._publish(round_id, evt)
        except Exception:
            logger.exception("Chat background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch._running_tasks[f"chat_{story_id}"] = task


@router.post("/projects/{project_id}/stories")
async def create_story(
    project_id: int, req: CreateStoryRequest, db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
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
    story_id = story.id
    # Trigger preparing stage in background (after this request's DB session commits)
    _start_ai_stage(story_id, orch)
    return {"id": story_id, "status": story.status.value}


@router.get("/stories/{story_id}")
async def get_story(
    story_id: int, db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    result = await db.execute(
        select(Story)
        .where(Story.id == story_id)
        .options(
            selectinload(Story.project),
            selectinload(Story.tasks),
            selectinload(Story.rounds).selectinload(Round.pull_requests),
            selectinload(Story.clarifications),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    active_round = next((r for r in story.rounds if r.status == RoundStatus.active), None)

    # Read doc content from files (DB stores paths)
    prd_content = read_doc(story.project, story, "prd.md") if story.prd else None
    td_content = read_doc(story.project, story, "technical_design.md") if story.technical_design else None
    dd_content = read_doc(story.project, story, "detailed_design.md") if story.detailed_design else None

    return {
        "id": story.id,
        "title": story.title,
        "status": story.status.value,
        "feature_tag": story.feature_tag,
        "raw_input": story.raw_input,
        "prd": prd_content,
        "confirmed_prd": story.confirmed_prd,
        "technical_design": td_content,
        "detailed_design": dd_content,
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
        "ai_running": (
            str(story_id) in orch._running_tasks
            or f"chat_{story_id}" in orch._running_tasks
        ),
        "ai_stage_running": str(story_id) in orch._running_tasks,
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
    await db.flush()

    # Trigger next AI stage if applicable
    ai_stages = {"clarifying", "planning", "designing", "coding"}
    if next_status in ai_stages:
        _start_ai_stage(story.id, orch)

    return {"id": story.id, "status": next_status}


@router.post("/stories/{story_id}/reject")
async def reject_stage(story_id: int, db: AsyncSession = Depends(get_db),
                       orch: Orchestrator = Depends(get_orch)):
    """Reject current stage output and re-trigger AI execution."""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404
    _start_ai_stage(story.id, orch)
    return {"id": story.id, "status": story.status.value, "message": "Stage re-triggered"}


# Fields/files to clear when rolling back to a given stage.
# db_fields: Story model fields to set to None
# doc_files: filenames to delete from workspace
_ROLLBACK_CLEAR: dict[str, dict] = {
    "preparing": {
        "db_fields": ["confirmed_prd", "technical_design", "detailed_design"],
        "doc_files": ["technical_design.md", "detailed_design.md"],
    },
    "clarifying": {
        "db_fields": ["technical_design", "detailed_design"],
        "doc_files": ["technical_design.md", "detailed_design.md"],
    },
    "planning": {
        "db_fields": ["detailed_design"],
        "doc_files": ["detailed_design.md"],
    },
    "designing": {
        "db_fields": [],
        "doc_files": [],
    },
}


@router.post("/stories/{story_id}/rollback")
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

    # Clear clarifications when rolling back to preparing (they get regenerated)
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

    _start_ai_stage(story.id, orch)
    return {"id": story.id, "status": target}


@router.post("/stories/{story_id}/answer")
async def answer_questions(
    story_id: int, req: AnswerRequest,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Answer clarification questions — update existing records, then trigger AI."""
    updated = 0
    for qa in req.answers:
        if qa.id:
            result = await db.execute(
                update(Clarification)
                .where(Clarification.id == qa.id, Clarification.story_id == story_id)
                .values(answer=qa.answer)
            )
            updated += result.rowcount
        else:
            # Fallback: match by question text
            result = await db.execute(
                update(Clarification)
                .where(
                    Clarification.story_id == story_id,
                    Clarification.question == qa.question,
                    Clarification.answer.is_(None),
                )
                .values(answer=qa.answer)
            )
            updated += result.rowcount
    await db.flush()

    # Build a summary of answers and trigger chat AI so the discussion continues
    summary_parts = [f"Q: {qa.question}\nA: {qa.answer}" for qa in req.answers]
    summary = "用户回答了以下澄清问题：\n\n" + "\n\n".join(summary_parts)
    _start_chat_ai(story_id, summary, orch)

    return {"message": "Answers recorded", "count": updated}


@router.put("/stories/{story_id}/prd")
async def update_prd(
    story_id: int, req: UpdatePrdRequest, db: AsyncSession = Depends(get_db),
):
    """Save manual PRD edits — writes to file, stores path in DB."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    status = story.status.value if not isinstance(story.status, str) else story.status
    if status not in ("preparing", "clarifying"):
        raise HTTPException(status_code=400, detail="PRD can only be edited in preparing/clarifying stages")
    rel_path = write_doc(story.project, story, "prd.md", req.prd)
    story.prd = rel_path
    return {"id": story.id, "prd": story.prd}


@router.post("/stories/{story_id}/chat")
async def chat_message(
    story_id: int, req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Send a user message to refine document via AI conversation."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.rounds))
    )
    story = result.scalar_one_or_none()
    if not story:
        return {"error": "Story not found"}, 404
    status = story.status.value if not isinstance(story.status, str) else story.status
    chat_stages = ("preparing", "clarifying", "planning", "designing")
    if status not in chat_stages:
        return {"error": f"Chat only available in {'/'.join(chat_stages)} stages"}, 400

    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None,
    )
    if not active_round:
        return {"error": "No active round"}, 404

    # Save user message
    db.add(AIMessage(
        round_id=active_round.id, role=AIMessageRole.user, content=req.message,
    ))
    await db.flush()

    _start_chat_ai(story.id, req.message, orch)
    return {"status": "processing"}


@router.post("/stories/{story_id}/iterate")
async def iterate_story(story_id: int, db: AsyncSession = Depends(get_db),
                        orch: Orchestrator = Depends(get_orch)):
    """Iterate: go back to coding with same branch/PR."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.rounds))
    )
    story = result.scalar_one_or_none()
    if not story or story.status != StoryStatus.verifying:
        return {"error": "Can only iterate from verifying status"}, 400

    story.status = StoryStatus.coding
    await db.flush()
    _start_ai_stage(story.id, orch)
    return {"id": story.id, "status": "coding", "action": "iterate"}


@router.post("/stories/{story_id}/restart")
async def restart_story(story_id: int, db: AsyncSession = Depends(get_db),
                        orch: Orchestrator = Depends(get_orch)):
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
    await db.flush()
    _start_ai_stage(story.id, orch)
    return {"id": story.id, "status": "designing", "action": "restart"}


@router.post("/stories/{story_id}/stop")
async def stop_story(story_id: int, orch: Orchestrator = Depends(get_orch)):
    """Emergency stop current AI task."""
    # Find active round and stop its task
    # For now, try to stop by story_id
    stopped = orch.stop_task(str(story_id))
    return {"stopped": stopped}


@router.get("/stories/{story_id}/stream")
async def stream_messages(story_id: int, mode: str = "",
                          db: AsyncSession = Depends(get_db),
                          orch: Orchestrator = Depends(get_orch)):
    """SSE endpoint: replay history then stream live AI messages.

    Query params:
        mode=chat  — only replay chat messages (skip initial stage execution output)
    """
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
    chat_only = mode == "chat"

    async def event_generator():
        # 1. Replay historical messages
        msg_result = await db.execute(
            select(AIMessage)
            .where(AIMessage.round_id == active_round.id)
            .order_by(AIMessage.created_at)
        )
        all_msgs = msg_result.scalars().all()

        if chat_only:
            # Only replay messages starting from the first user message
            replay = False
            for msg in all_msgs:
                if msg.role == AIMessageRole.user:
                    replay = True
                if replay:
                    event = {"type": msg.role.value, "content": msg.content}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        else:
            for msg in all_msgs:
                event = {"type": msg.role.value, "content": msg.content}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 2. Subscribe to live messages
        queue = orch.subscribe(round_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") == "error":
                        break
                    # Chat mode: keep stream alive after "done" for subsequent AI runs
                    if event.get("type") == "done" and not chat_only:
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


# ---------------------------------------------------------------------------
# Story docs API (file-based)
# ---------------------------------------------------------------------------


@router.get("/stories/{story_id}/docs")
async def list_story_docs(story_id: int, db: AsyncSession = Depends(get_db)):
    """List document files for a story."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    files = list_docs(story.project, story)
    return {"files": files}


@router.get("/stories/{story_id}/docs/{filename}")
async def get_story_doc(story_id: int, filename: str, db: AsyncSession = Depends(get_db)):
    """Read a story document file."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    content = read_doc(story.project, story, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"filename": filename, "content": content}


@router.put("/stories/{story_id}/docs/{filename}")
async def save_story_doc(
    story_id: int, filename: str, req: UpdateDocRequest,
    db: AsyncSession = Depends(get_db),
):
    """Write a story document file, store path in DB."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    rel_path = write_doc(story.project, story, filename, req.content)
    # Update the corresponding DB field if it maps to a known doc
    field_map = {"prd.md": "prd", "technical_design.md": "technical_design",
                 "detailed_design.md": "detailed_design"}
    db_field = field_map.get(filename)
    if db_field:
        setattr(story, db_field, rel_path)
    return {"filename": filename, "path": rel_path}
