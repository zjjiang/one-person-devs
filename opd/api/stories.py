"""Story lifecycle API routes — core CRUD, confirm/reject, chat, stream, preflight."""

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
from opd.api.stories_tasks import _get_site_url, _start_ai_stage, _start_chat_ai
from opd.db.models import (
    AIMessage,
    AIMessageRole,
    Clarification,
    NotificationType,
    Project,
    Round,
    RoundStatus,
    Story,
    StoryStatus,
    WorkspaceStatus,
)
from opd.db.session import get_session_factory
from opd.engine.hashing import should_skip_ai
from opd.engine.notify import send_notification
from opd.engine.orchestrator import Orchestrator
from opd.engine.state_machine import ensure_status_value
from opd.engine.workspace import read_doc, resolve_work_dir, write_doc
from opd.models.schemas import (
    AnswerRequest,
    ChatRequest,
    CreateStoryRequest,
    UpdatePrdRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stories"])


@router.post("/projects/{project_id}/stories")
async def create_story(
    project_id: int, req: CreateStoryRequest, db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    # Preflight: workspace must be ready
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.workspace_status != WorkspaceStatus.ready:
        raise HTTPException(status_code=400, detail="工作区未就绪，请先初始化工作区")
    if not (resolve_work_dir(project) / "CLAUDE.md").is_file():
        raise HTTPException(
            status_code=400,
            detail="工作区中缺少 CLAUDE.md，请先在工作区目录下执行 claude /init 生成",
        )

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
    round_ = Round(
        story_id=story.id, round_number=1, type="initial", status=RoundStatus.active
    )
    db.add(round_)
    await db.flush()
    story_id = story.id
    _start_ai_stage(story_id, orch, project_id=project_id)
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

    prd_content = read_doc(story.project, story, "prd.md") if story.prd else None
    td_content = (
        read_doc(story.project, story, "technical_design.md") if story.technical_design else None
    )
    dd_content = (
        read_doc(story.project, story, "detailed_design.md") if story.detailed_design else None
    )
    cr_content = (
        read_doc(story.project, story, "coding_report.md") if story.coding_report else None
    )
    tg_content = read_doc(story.project, story, "test_guide.md") if story.test_guide else None

    return {
        "id": story.id,
        "project_id": story.project_id,
        "project_name": story.project.name,
        "title": story.title,
        "status": story.status.value,
        "feature_tag": story.feature_tag,
        "repo_url": story.project.repo_url,
        "raw_input": story.raw_input,
        "prd": prd_content,
        "confirmed_prd": story.confirmed_prd,
        "technical_design": td_content,
        "detailed_design": dd_content,
        "coding_report": cr_content,
        "test_guide": tg_content,
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
            orch.is_task_running(str(story_id))
            or orch.is_task_running(f"chat_{story_id}")
        ),
        "ai_stage_running": orch.is_task_running(str(story_id)),
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
        raise HTTPException(status_code=404, detail="Story not found")

    status = ensure_status_value(story.status)
    next_status_map = {
        "preparing": "clarifying",
        "clarifying": "planning",
        "planning": "designing",
        "designing": "coding",
        "verifying": "done",
    }
    if status not in next_status_map:
        raise HTTPException(status_code=400, detail=f"Cannot confirm in status: {status}")

    next_status = next_status_map[status]

    # Block concurrent coding within the same project
    if next_status == "coding" and orch.has_coding_task(story.project_id):
        raise HTTPException(
            status_code=409,
            detail="该项目已有 Story 在编码中，请等待完成",
        )

    if status == "clarifying" and not story.confirmed_prd:
        story.confirmed_prd = story.prd

    story.status = next_status
    await db.flush()

    ai_stages = {"clarifying", "planning", "designing", "coding"}
    skipped_ai = False
    if next_status in ai_stages:
        if should_skip_ai(story, story.project, next_status):
            skipped_ai = True
            logger.info(
                "Skipping AI for stage [%s] story %s — input unchanged",
                next_status, story_id,
            )
        else:
            _start_ai_stage(story.id, orch, project_id=story.project_id)

    # Notify when story is marked done (verifying → done)
    if next_status == "done":
        story_link = f"{_get_site_url()}/projects/{story.project_id}/stories/{story_id}"
        asyncio.create_task(send_notification(
            get_session_factory(), NotificationType.story_done,
            f"Story #{story_id}「{story.title}」已完成 ✅",
            f"需求 #{story_id}「{story.title}」已通过验证，流程完结。",
            story_link, orch.capabilities,
            story_id=story_id, project_id=story.project_id,
        ))

    return {"id": story.id, "status": next_status, "skipped_ai": skipped_ai}


@router.post("/stories/{story_id}/reject")
async def reject_stage(story_id: int, db: AsyncSession = Depends(get_db),
                       orch: Orchestrator = Depends(get_orch)):
    """Reject current stage output and re-trigger AI execution."""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    _start_ai_stage(story.id, orch, project_id=story.project_id)
    return {"id": story.id, "status": story.status.value, "message": "Stage re-triggered"}


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
    status = ensure_status_value(story.status)
    if status not in ("preparing", "clarifying"):
        raise HTTPException(
            status_code=400, detail="PRD can only be edited in preparing/clarifying stages"
        )
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
        raise HTTPException(status_code=404, detail="Story not found")
    status = ensure_status_value(story.status)
    chat_stages = ("preparing", "clarifying", "planning", "designing")
    if status not in chat_stages:
        raise HTTPException(
            status_code=400, detail=f"Chat only available in {'/'.join(chat_stages)} stages"
        )

    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None,
    )
    if not active_round:
        raise HTTPException(status_code=404, detail="No active round")

    db.add(AIMessage(
        round_id=active_round.id, role=AIMessageRole.user, content=req.message,
    ))
    await db.flush()

    _start_chat_ai(story.id, req.message, orch, project_id=story.project_id)
    return {"status": "processing"}


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
        raise HTTPException(status_code=404, detail="Story not found")

    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None
    )
    if not active_round:
        raise HTTPException(status_code=404, detail="No active round")

    round_id = str(active_round.id)
    chat_only = mode == "chat"

    async def event_generator():
        msg_result = await db.execute(
            select(AIMessage)
            .where(AIMessage.round_id == active_round.id)
            .order_by(AIMessage.created_at)
        )
        all_msgs = msg_result.scalars().all()

        from opd.engine.ai_message_storage import read_ai_message_content

        if chat_only:
            replay = False
            for msg in all_msgs:
                if msg.role == AIMessageRole.user:
                    replay = True
                if replay:
                    try:
                        content = read_ai_message_content(msg, story.project)
                        event = {"type": msg.role.value, "content": content}
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    except ValueError as e:
                        logger.error("Failed to read message %s: %s", msg.id, e)
                        error_event = {"type": "error", "content": f"消息读取失败: {e}"}
                        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        else:
            for msg in all_msgs:
                try:
                    content = read_ai_message_content(msg, story.project)
                    event = {"type": msg.role.value, "content": content}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except ValueError as e:
                    logger.error("Failed to read message %s: %s", msg.id, e)
                    error_event = {"type": "error", "content": f"消息读取失败: {e}"}
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

        queue = orch.subscribe(round_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") == "error":
                        break
                    if event.get("type") == "done" and not chat_only:
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            orch.unsubscribe(round_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/stories/{story_id}/preflight")
async def preflight_check(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Check capability health and workspace lock for the next stage."""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    status = ensure_status_value(story.status)

    # Check workspace lock if entering coding stage
    if status == "coding":
        from opd.engine.workspace_lock import check_workspace_lock

        locked_by = await check_workspace_lock(db, story.project_id)
        if locked_by and locked_by != story_id:
            # Query locking story info
            stmt = select(Story).where(Story.id == locked_by)
            result = await db.execute(stmt)
            locked_story = result.scalar_one_or_none()

            return {
                "ok": False,
                "can_start": False,
                "reason": "workspace_locked",
                "locked_by_story_id": locked_by,
                "locked_by_story_title": locked_story.title if locked_story else None,
                "errors": [f"工作区被 Story #{locked_by} 占用"],
                "warnings": [],
            }

    stage = orch.get_stage(status)
    if not stage:
        return {"capabilities": {}, "ok": True, "can_start": True, "errors": [], "warnings": []}

    preflight = await orch.capabilities.preflight(
        stage.required_capabilities, stage.optional_capabilities
    )
    return {
        "ok": preflight.ok,
        "can_start": preflight.ok,
        "errors": preflight.errors,
        "warnings": preflight.warnings,
    }
