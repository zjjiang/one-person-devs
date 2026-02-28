"""Background AI task functions for story lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from opd.capabilities.registry import build_capability_overrides
from opd.config import load_config
from opd.db.models import (
    AIMessage,
    AIMessageRole,
    Clarification,
    NotificationType,
    Project,
    ProjectCapabilityConfig,
    PullRequest,
    Round,
    RoundStatus,
    Story,
)
from opd.db.session import get_session_factory
from opd.engine.context import (
    build_clarifying_chat_prompt,
    build_designing_chat_prompt,
    build_planning_chat_prompt,
    build_refine_prd_prompt,
    parse_refine_response,
)
from opd.engine.hashing import STAGE_INPUT_MAP, compute_stage_input_hash
from opd.engine.notify import send_notification
from opd.engine.orchestrator import Orchestrator
from opd.engine.stages.base import StageContext
from opd.engine.state_machine import ensure_status_value
from opd.engine.workspace import (
    DOC_FIELD_MAP,
    create_coding_branch,
    generate_branch_name,
    resolve_work_dir,
    write_doc,
)

logger = logging.getLogger(__name__)

_site_url: str | None = None


def _get_site_url() -> str:
    global _site_url
    if _site_url is None:
        _site_url = load_config().server.site_url.rstrip("/")
    return _site_url

_STAGE_LABELS: dict[str, str] = {
    "preparing": "需求分析",
    "clarifying": "需求澄清",
    "planning": "技术方案",
    "designing": "详细设计",
    "coding": "编码",
    "verifying": "人工验证",
}


async def _post_coding_create_pr(
    db, story: Story, active_round: Round, registry,
) -> None:
    """After coding succeeds: commit, push, and create a PR."""
    branch = active_round.branch_name
    if not branch:
        logger.warning("No branch for story %s, skipping PR creation", story.id)
        return

    scm_cap = registry.get("scm")
    if not scm_cap:
        logger.warning("SCM capability not available, skipping PR creation for story %s", story.id)
        return

    work_dir = str(resolve_work_dir(story.project))
    repo_url = story.project.repo_url

    try:
        await scm_cap.provider.commit_and_push(
            work_dir, branch, f"feat: {story.title} (story #{story.id})",
        )
        logger.info("Committed and pushed branch %s for story %s", branch, story.id)
    except Exception:
        logger.warning("commit_and_push failed for story %s", story.id, exc_info=True)
        return

    try:
        pr_info = await scm_cap.provider.create_pull_request(
            repo_url, branch,
            title=f"[OPD] {story.title}",
            body=f"Auto-created by OPD for Story #{story.id}",
        )
        db.add(PullRequest(
            round_id=active_round.id,
            pr_number=pr_info["pr_number"],
            pr_url=pr_info["pr_url"],
        ))
        logger.info("Created PR #%s for story %s", pr_info["pr_number"], story.id)
        return pr_info
    except Exception:
        logger.warning("create_pull_request failed for story %s", story.id, exc_info=True)
        return None


def _save_clarifications(db, story: Story, raw_text: str) -> None:
    """Parse AI-generated questions JSON and save as Clarification records."""
    json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
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


async def _build_project_registry(db, orch: Orchestrator, project_id: int):
    """Load project capability configs and build overridden registry."""
    cap_result = await db.execute(
        select(ProjectCapabilityConfig)
        .where(ProjectCapabilityConfig.project_id == project_id)
    )
    cap_configs = cap_result.scalars().all()
    registry = orch.capabilities
    if cap_configs:
        overrides = build_capability_overrides(cap_configs)
        registry = await orch.capabilities.with_project_overrides(overrides)
    return registry


def _start_ai_stage(story_id: int, orch: Orchestrator,
                    project_id: int | None = None) -> None:
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

                    registry = await _build_project_registry(
                        db, orch, story.project_id,
                    )

                    status = ensure_status_value(story.status)
                    stage = orch.get_stage(status)
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
                        await orch.publish(round_id, event)
                        msg_type = event.get("type", "")
                        content = event.get("content", "")
                        if msg_type in ("assistant", "tool") and content:
                            from opd.engine.ai_message_storage import write_ai_message_content

                            # Create message with placeholder
                            msg = AIMessage(
                                round_id=active_round.id,
                                role=AIMessageRole(msg_type),
                                content="",  # Will be set by storage layer
                            )
                            db.add(msg)
                            await db.flush()  # Get message ID

                            # Write content using hybrid storage
                            storage_fields = write_ai_message_content(
                                story.project, active_round.id, msg.id, content
                            )
                            for field, value in storage_fields.items():
                                setattr(msg, field, value)

                    ctx = StageContext(
                        story=story, project=story.project, round=active_round,
                        capabilities=registry, publish=publish,
                    )

                    # Acquire workspace lock when entering coding stage
                    if status == "coding":
                        from opd.api.stories_task_helpers import (
                            acquire_workspace_lock_for_coding,
                        )

                        success, error_msg = await acquire_workspace_lock_for_coding(
                            db, story, story_id, round_id, orch
                        )
                        if not success:
                            orch.unregister_task(str(story_id))
                            return

                    # Create coding branch if entering coding stage without one
                    if status == "coding":
                        from opd.api.stories_task_helpers import (
                            create_coding_branch_if_needed,
                        )

                        await create_coding_branch_if_needed(
                            active_round, story, orch, session_factory
                        )

                    done_event: dict | None = None
                    pr_created = False
                    generated_docs: list[tuple[str, str]] = []  # (filename, content)
                    try:
                        stage_result = await stage.execute(ctx)
                        if stage_result.success:
                            for fld, filename in DOC_FIELD_MAP.items():
                                if fld in stage_result.output:
                                    content = stage_result.output[fld]
                                    rel_path = write_doc(
                                        story.project, story, filename, content,
                                    )
                                    setattr(story, fld, rel_path)
                                    generated_docs.append((filename, content))
                            if "questions" in stage_result.output:
                                _save_clarifications(
                                    db, story, stage_result.output["questions"],
                                )
                            logger.info("Stage [%s] completed for story %s",
                                        status, story_id)
                            if stage_result.next_status:
                                story.status = stage_result.next_status
                            input_hash = compute_stage_input_hash(
                                story, story.project, status,
                            )
                            if input_hash and status in STAGE_INPUT_MAP:
                                hash_field = STAGE_INPUT_MAP[status][2]
                                setattr(story, hash_field, input_hash)
                            # Auto-create PR after coding completes
                            if status == "coding":
                                pr_info = await _post_coding_create_pr(
                                    db, story, active_round, registry,
                                )
                                pr_created = pr_info is not None
                                # Release workspace lock after coding completes
                                from opd.api.stories_task_helpers import (
                                    release_workspace_lock_for_coding,
                                )

                                await release_workspace_lock_for_coding(
                                    db, story.project_id, story_id
                                )
                            done_event = {"type": "done"}
                        else:
                            error_msg = "; ".join(stage_result.errors)
                            logger.error("Stage [%s] failed: %s", status, error_msg)
                            done_event = {"type": "error", "content": error_msg}
                            # Release lock on error if in coding stage
                            if status == "coding":
                                from opd.api.stories_task_helpers import (
                                    release_workspace_lock_for_coding,
                                )

                                await release_workspace_lock_for_coding(
                                    db, story.project_id, story_id
                                )
                    except Exception as e:
                        logger.exception("AI stage exception for story %s", story_id)
                        done_event = {"type": "error", "content": str(e)}
                        # Release lock on exception if in coding stage
                        if status == "coding":
                            from opd.api.stories_task_helpers import (
                                release_workspace_lock_for_coding,
                            )

                            await release_workspace_lock_for_coding(
                                db, story.project_id, story_id
                            )
                    finally:
                        orch.unregister_task(str(story_id))
            # Transaction committed — publish done/error so frontend reads fresh data
            if done_event:
                await orch.publish(round_id, done_event)
            # Send notifications after commit
            stage_label = _STAGE_LABELS.get(status, status)
            story_link = f"{_get_site_url()}/projects/{project_id}/stories/{story_id}"
            if done_event and done_event.get("type") == "done":
                # Pick the primary generated doc for file attachment
                doc_content = None
                doc_filename = None
                if generated_docs:
                    doc_filename, doc_content = generated_docs[0]
                await send_notification(
                    session_factory, NotificationType.stage_completed,
                    f"Story #{story_id}「{story.title}」{stage_label}完成",
                    f"需求 #{story_id}「{story.title}」的{stage_label}阶段已完成，可以继续下一步。",
                    story_link, orch.capabilities,
                    story_id=story_id, project_id=project_id,
                    doc_content=doc_content, doc_filename=doc_filename,
                )
                if pr_created:
                    await send_notification(
                        session_factory, NotificationType.pr_created,
                        f"Story #{story_id}「{story.title}」PR 已创建",
                        f"需求 #{story_id}「{story.title}」的合并请求已自动创建，请前往审查。",
                        story_link, orch.capabilities,
                        story_id=story_id, project_id=project_id,
                    )
            elif done_event and done_event.get("type") == "error":
                error_content = done_event.get("content", "未知错误")
                await send_notification(
                    session_factory, NotificationType.stage_failed,
                    f"Story #{story_id}「{story.title}」{stage_label}失败",
                    f"需求 #{story_id}「{story.title}」的{stage_label}阶段执行失败：{error_content}",
                    story_link, orch.capabilities,
                    story_id=story_id, project_id=project_id,
                )
        except Exception:
            logger.exception("Background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch.register_task(str(story_id), task,
                       project_id=project_id, task_type="ai_stage")


def _start_chat_ai(story_id: int, user_message: str, orch: Orchestrator,
                   project_id: int | None = None) -> None:
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

                    registry = await _build_project_registry(
                        db, orch, story.project_id,
                    )

                    ai = registry.get("ai")
                    if not ai:
                        await orch.publish(
                            round_id, {"type": "error", "content": "AI capability not available"}
                        )
                        return

                    # Build prompt based on stage
                    status = ensure_status_value(story.status)
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
                    work_dir = str(resolve_work_dir(story.project))
                    try:
                        async for msg in ai.provider.refine_prd(
                            system_prompt, user_prompt, work_dir,
                        ):
                            if msg.get("type") == "assistant" and msg.get("content"):
                                collected.append(msg["content"])

                        full_text = "\n".join(collected)
                        discussion, updated_doc = parse_refine_response(full_text)

                        if discussion:
                            from opd.engine.ai_message_storage import write_ai_message_content

                            msg = AIMessage(
                                round_id=active_round.id,
                                role=AIMessageRole.assistant,
                                content="",
                            )
                            db.add(msg)
                            await db.flush()

                            storage_fields = write_ai_message_content(
                                story.project, active_round.id, msg.id, discussion
                            )
                            for field, value in storage_fields.items():
                                setattr(msg, field, value)

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
                        orch.unregister_task(f"chat_{story_id}")
            # Transaction committed — publish final events
            for evt in post_commit_events:
                await orch.publish(round_id, evt)
        except Exception:
            logger.exception("Chat background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch.register_task(f"chat_{story_id}", task,
                       project_id=project_id, task_type="chat")
