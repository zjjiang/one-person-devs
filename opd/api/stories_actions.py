"""Story state-transition action routes: rollback, iterate, restart, stop."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.api.stories_tasks import _build_project_registry, _get_site_url, _start_ai_stage
from opd.db.models import (
    AIMessage,
    NotificationType,
    PRStatus,
    PullRequest,
    Round,
    RoundStatus,
    RoundType,
    Story,
    StoryStatus,
)
from opd.db.session import get_session_factory
from opd.engine.notify import send_notification
from opd.engine.orchestrator import Orchestrator
from opd.engine.workspace import delete_doc, discard_branch, pull_main, resolve_work_dir

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
    _start_ai_stage(story.id, orch, project_id=story.project_id)
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
            async with orch.get_workspace_lock(story.project_id):
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
async def stop_story(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Emergency stop current AI task."""
    stopped = orch.stop_task(str(story_id))

    # Try to release workspace lock if story holds it
    try:
        result = await db.execute(select(Story).where(Story.id == story_id))
        story = result.scalar_one_or_none()

        if story and story.has_workspace_lock:
            from opd.engine.workspace_lock import release_workspace_lock

            try:
                await release_workspace_lock(db, story.project_id, story_id)
                logger.info("Released workspace lock for stopped story %s", story_id)
            except Exception:
                logger.warning(
                    "Failed to release workspace lock for stopped story %s",
                    story_id, exc_info=True,
                )
    except Exception:
        # Don't fail stop operation if lock release fails
        logger.warning("Error checking/releasing lock for story %s", story_id, exc_info=True)

    return {"stopped": stopped}


@actions_router.post("/stories/{story_id}/merge")
async def merge_story_pr(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Merge the open PR for a story."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(
            selectinload(Story.project),
            selectinload(Story.rounds).selectinload(Round.pull_requests),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.status not in (StoryStatus.verifying, StoryStatus.done):
        raise HTTPException(status_code=400, detail="只能在验证或完成阶段合并 PR")

    # Find the open PR on the active round
    open_pr: PullRequest | None = None
    for rnd in story.rounds:
        for pr in rnd.pull_requests:
            if pr.status == PRStatus.open:
                open_pr = pr
                break
        if open_pr:
            break

    if not open_pr:
        raise HTTPException(status_code=400, detail="没有可合并的 PR")

    registry = await _build_project_registry(db, orch, story.project_id)
    scm_cap = registry.get("scm")
    if not scm_cap:
        raise HTTPException(status_code=400, detail="SCM 能力未配置")

    try:
        await scm_cap.provider.merge_pull_request(
            story.project.repo_url, open_pr.pr_number,
        )
        open_pr.status = PRStatus.merged
    except Exception as e:
        logger.exception("Failed to merge PR #%s for story %s", open_pr.pr_number, story_id)
        raise HTTPException(status_code=500, detail=f"合并失败: {e}")

    # Pull main to keep workspace up to date
    try:
        async with orch.get_workspace_lock(story.project_id):
            await pull_main(story.project)
    except Exception:
        logger.warning("pull_main failed after merge for story %s", story_id, exc_info=True)

    await db.flush()

    # Notify merge success
    story_link = f"{await _get_site_url()}/projects/{story.project_id}/stories/{story_id}"
    try:
        await send_notification(
            get_session_factory(), NotificationType.pr_merged,
            f"Story #{story_id}「{story.title}」PR 已合并",
            f"需求 #{story_id}「{story.title}」的 PR #{open_pr.pr_number} 已成功合并到主分支。",
            story_link, orch.capabilities,
            story_id=story_id, project_id=story.project_id,
        )
    except Exception:
        logger.warning("Notification failed for merge story %s", story_id, exc_info=True)

    return {"id": story.id, "pr_number": open_pr.pr_number, "status": "merged"}


@actions_router.post("/stories/{story_id}/create-pr")
async def create_story_pr(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Retry: commit, push, and create a PR for the story's active branch."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(
            selectinload(Story.project),
            selectinload(Story.rounds).selectinload(Round.pull_requests),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find active round with a branch
    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None,
    )
    if not active_round or not active_round.branch_name:
        raise HTTPException(status_code=400, detail="没有可用的分支")

    # Check if PR already exists
    existing_pr = next(
        (pr for pr in active_round.pull_requests if pr.status == PRStatus.open),
        None,
    )
    if existing_pr:
        raise HTTPException(
            status_code=400,
            detail=f"PR #{existing_pr.pr_number} 已存在",
        )

    registry = await _build_project_registry(db, orch, story.project_id)
    scm_cap = registry.get("scm")
    if not scm_cap:
        raise HTTPException(status_code=400, detail="SCM 能力未配置")

    branch = active_round.branch_name
    work_dir = str(resolve_work_dir(story.project))

    # Commit and push
    try:
        await scm_cap.provider.commit_and_push(
            work_dir, branch, f"feat: {story.title} (story #{story.id})",
        )
    except Exception as e:
        logger.exception("commit_and_push failed for story %s", story_id)
        raise HTTPException(status_code=500, detail=f"Push 失败: {e}")

    # Create PR
    try:
        pr_info = await scm_cap.provider.create_pull_request(
            story.project.repo_url, branch,
            title=f"[OPD] {story.title}",
            body=f"Auto-created by OPD for Story #{story.id}",
        )
        db.add(PullRequest(
            round_id=active_round.id,
            pr_number=pr_info["pr_number"],
            pr_url=pr_info["pr_url"],
        ))
        await db.flush()
        logger.info("Created PR #%s for story %s", pr_info["pr_number"], story_id)
        return {
            "id": story.id,
            "pr_number": pr_info["pr_number"],
            "pr_url": pr_info["pr_url"],
        }
    except Exception as e:
        logger.exception("create_pull_request failed for story %s", story_id)
        raise HTTPException(status_code=500, detail=f"创建 PR 失败: {e}")
