"""Background AI task functions for story lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from opd.capabilities.registry import build_capability_overrides
from opd.db.models import (
    AIMessage,
    AIMessageRole,
    Clarification,
    Project,
    ProjectCapabilityConfig,
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
from opd.engine.orchestrator import Orchestrator
from opd.engine.stages.base import StageContext
from opd.engine.state_machine import ensure_status_value
from opd.engine.workspace import (
    DOC_FIELD_MAP,
    create_coding_branch,
    generate_branch_name,
    write_doc,
)

logger = logging.getLogger(__name__)


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
                            db.add(AIMessage(
                                round_id=active_round.id,
                                role=AIMessageRole(msg_type),
                                content=content,
                            ))

                    ctx = StageContext(
                        story=story, project=story.project, round=active_round,
                        capabilities=registry, publish=publish,
                    )

                    # Create coding branch if entering coding stage without one
                    if status == "coding" and not active_round.branch_name:
                        branch = generate_branch_name(
                            story.id, active_round.round_number,
                        )
                        try:
                            await create_coding_branch(story.project, branch)
                            active_round.branch_name = branch
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

                    done_event: dict | None = None
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
                            done_event = {"type": "done"}
                        else:
                            error_msg = "; ".join(stage_result.errors)
                            logger.error("Stage [%s] failed: %s", status, error_msg)
                            done_event = {"type": "error", "content": error_msg}
                    except Exception as e:
                        logger.exception("AI stage exception for story %s", story_id)
                        done_event = {"type": "error", "content": str(e)}
                    finally:
                        orch.unregister_task(str(story_id))
            # Transaction committed — publish done/error so frontend reads fresh data
            if done_event:
                await orch.publish(round_id, done_event)
        except Exception:
            logger.exception("Background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch.register_task(str(story_id), task)


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
                    try:
                        async for msg in ai.provider.refine_prd(system_prompt, user_prompt):
                            if msg.get("type") == "assistant" and msg.get("content"):
                                collected.append(msg["content"])

                        full_text = "\n".join(collected)
                        discussion, updated_doc = parse_refine_response(full_text)

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
                        orch.unregister_task(f"chat_{story_id}")
            # Transaction committed — publish final events
            for evt in post_commit_events:
                await orch.publish(round_id, evt)
        except Exception:
            logger.exception("Chat background task crashed for story %s", story_id)

    task = asyncio.create_task(_run())
    orch.register_task(f"chat_{story_id}", task)
