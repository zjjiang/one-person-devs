"""Core orchestration engine for OPD.

The :class:`Orchestrator` coordinates providers, the state machine, and
database operations to drive a Story through its lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.db.models import (
    AIMessage,
    AIMessageRole,
    Clarification,
    PRStatus,
    Project,
    Round,
    RoundStatus,
    RoundType,
    Story,
    StoryStatus,
)
from opd.engine.context import (
    build_coding_prompt,
    build_plan_prompt,
    build_revision_prompt,
    build_system_prompt,
)
from opd.engine.state_machine import InvalidTransitionError, StateMachine

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Base exception for orchestrator-level errors."""


class StoryNotFoundError(OrchestratorError):
    """Raised when a story cannot be found."""


class ProjectNotFoundError(OrchestratorError):
    """Raised when a project cannot be found."""


class RoundNotFoundError(OrchestratorError):
    """Raised when the active round cannot be found."""


class Orchestrator:
    """Drives a Story through its lifecycle.

    Parameters
    ----------
    providers:
        A dict mapping provider names (``"ai"``, ``"scm"``, etc.) to
        provider instances.
    workspace_dir:
        Base directory for cloned repos / AI work directories.
    """

    def __init__(
        self,
        providers: dict[str, Any],
        workspace_dir: str = "./workspace",
    ) -> None:
        self.providers = providers
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.sm = StateMachine()

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    @property
    def ai(self) -> Any | None:
        return self.providers.get("ai")

    @property
    def scm(self) -> Any | None:
        return self.providers.get("scm")

    @property
    def ci(self) -> Any | None:
        return self.providers.get("ci")

    def _work_dir(self, project: Project, story: Story) -> Path:
        """Return the workspace directory for a story."""
        safe_name = project.name.replace("/", "_").replace(" ", "_")
        d = self.workspace_dir / safe_name / story.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _build_requirement(self, story: Story, round_: Round) -> dict[str, Any]:
        """Build a requirement dict for the AI provider."""
        return {
            "title": story.title,
            "description": round_.requirement_snapshot or story.requirement,
            "acceptance_criteria": story.acceptance_criteria or "",
        }

    def _build_context(self, project: Project, round_: Round) -> dict[str, Any]:
        """Build a context dict for the AI provider."""
        ctx: dict[str, Any] = {
            "project_name": project.name,
            "repo_url": project.repo_url,
        }
        if project.tech_stack:
            ctx["tech_stack"] = project.tech_stack
        if project.architecture:
            ctx["architecture"] = project.architecture
        if project.description:
            ctx["description"] = project.description
        rules = [r.content for r in project.rules if r.enabled]
        if rules:
            ctx["rules"] = rules
        return ctx

    def _get_repo_name(self, project: Project) -> str:
        """Extract owner/repo from repo_url."""
        url = project.repo_url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        parts = url.split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
        return url

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_project(self, db: AsyncSession, project_id: str) -> Project:
        result = await db.execute(
            select(Project)
            .options(
                selectinload(Project.rules),
                selectinload(Project.skills),
            )
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _get_story(self, db: AsyncSession, story_id: str) -> Story:
        result = await db.execute(
            select(Story)
            .options(
                selectinload(Story.rounds).selectinload(Round.clarifications),
                selectinload(Story.rounds).selectinload(Round.ai_messages),
                selectinload(Story.project).selectinload(Project.rules),
            )
            .where(Story.id == story_id)
        )
        story = result.scalar_one_or_none()
        if story is None:
            raise StoryNotFoundError(f"Story {story_id} not found")
        return story

    def _active_round(self, story: Story) -> Round:
        if not story.rounds:
            raise RoundNotFoundError(f"Story {story.id} has no rounds")
        return max(story.rounds, key=lambda r: r.round_number)

    def _transition(self, round_: Round, target: RoundStatus) -> None:
        self.sm.transition(round_.status, target)
        round_.status = target

    # ------------------------------------------------------------------
    # Background task helpers
    # ------------------------------------------------------------------

    async def _run_plan_background(
        self,
        story_id: str,
        round_id: str,
        requirement: dict[str, Any],
        context: dict[str, Any],
        tag: str = "[Implementation Plan]",
    ) -> None:
        """Generate a plan in the background and save it as an AIMessage."""
        from opd.db.session import get_db

        try:
            plan = await self.ai.plan(requirement, context)
            plan_text = json.dumps(plan, indent=2, default=str)
            async for db in get_db():
                db.add(AIMessage(
                    round_id=round_id,
                    role=AIMessageRole.assistant,
                    content=f"{tag}\n{plan_text}",
                ))
                await db.flush()
            logger.info("Background plan generation completed for round %s", round_id)
        except Exception:
            logger.exception("Background plan generation failed for round %s", round_id)
            try:
                async for db in get_db():
                    db.add(AIMessage(
                        round_id=round_id,
                        role=AIMessageRole.assistant,
                        content="[Error] 方案生成失败，请查看服务器日志或重试。",
                    ))
                    await db.flush()
            except Exception:
                logger.exception("Failed to record error for round %s", round_id)

    async def _run_clarify_background(
        self,
        story_id: str,
        round_id: str,
        requirement: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """Run clarification in the background."""
        from opd.db.session import get_db

        try:
            questions = await self.ai.clarify(requirement, context)
            async for db in get_db():
                result = await db.execute(
                    select(Round).where(Round.id == round_id)
                )
                round_ = result.scalar_one_or_none()
                if round_ is None:
                    return
                for q in questions:
                    q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                    db.add(Clarification(round_id=round_id, question=q_text))
                if not questions:
                    self.sm.transition(round_.status, RoundStatus.planning)
                    round_.status = RoundStatus.planning
                await db.flush()
            logger.info("Background clarify completed for round %s", round_id)
        except Exception:
            logger.exception("Background clarify failed for round %s", round_id)
            try:
                async for db in get_db():
                    result = await db.execute(
                        select(Round).where(Round.id == round_id)
                    )
                    round_ = result.scalar_one_or_none()
                    if round_:
                        self.sm.transition(round_.status, RoundStatus.planning)
                        round_.status = RoundStatus.planning
                        await db.flush()
            except Exception:
                logger.exception("Failed to handle clarify error for round %s", round_id)

    async def _run_ai_background(
        self,
        task_name: str,
        story_id: str,
        round_id: str,
        coro_factory: Any,
        on_success_status: RoundStatus,
    ) -> None:
        """Run an AI task in the background with its own DB session.

        Parameters
        ----------
        task_name:
            Human-readable name for logging.
        story_id:
            Story ID for context.
        round_id:
            Round ID to update.
        coro_factory:
            An async callable that yields AI message dicts.
        on_success_status:
            The status to transition to when the task completes.
        """
        from opd.db.session import get_db

        try:
            async for db in get_db():
                result = await db.execute(
                    select(Round).where(Round.id == round_id)
                )
                round_ = result.scalar_one_or_none()
                if round_ is None:
                    logger.error("Background %s: round %s not found", task_name, round_id)
                    return

                messages_collected: list[str] = []
                async for msg in coro_factory():
                    content = msg.get("content", "")
                    msg_type = msg.get("type", "text")
                    if content and msg_type == "text":
                        messages_collected.append(content)
                        db.add(AIMessage(
                            round_id=round_id,
                            role=AIMessageRole.assistant,
                            content=content,
                        ))
                    elif msg_type == "tool_use":
                        tool_info = json.dumps({
                            "tool": msg.get("name", ""),
                            "input": msg.get("input", {}),
                        }, default=str)
                        db.add(AIMessage(
                            round_id=round_id,
                            role=AIMessageRole.tool,
                            content=tool_info,
                        ))

                # Transition to success status
                round_.status = on_success_status
                await db.flush()
                logger.info(
                    "Background %s completed for round %s -> %s",
                    task_name, round_id, on_success_status.value,
                )
        except Exception:
            logger.exception("Background %s failed for round %s", task_name, round_id)
            try:
                async for db in get_db():
                    db.add(AIMessage(
                        round_id=round_id,
                        role=AIMessageRole.assistant,
                        content=f"[Error] Background task '{task_name}' failed. Check server logs.",
                    ))
                    await db.flush()
            except Exception:
                logger.exception("Failed to record error message for round %s", round_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_project(
        self, db: AsyncSession, data: dict[str, Any]
    ) -> Project:
        project = Project(**data)
        db.add(project)
        await db.flush()
        await db.refresh(project)
        logger.info("Created project %s (%s)", project.id, project.name)
        return project

    async def create_story(
        self, db: AsyncSession, project_id: str, data: dict[str, Any]
    ) -> Story:
        """Create a new story and its first round, then trigger clarification."""
        project = await self._get_project(db, project_id)

        story = Story(project_id=project_id, **data)
        story.status = StoryStatus.in_progress
        story.current_round = 1
        db.add(story)
        await db.flush()

        round_ = Round(
            story_id=story.id, round_number=1, type=RoundType.initial,
            requirement_snapshot=story.requirement, status=RoundStatus.created,
        )
        db.add(round_)
        await db.flush()
        self._transition(round_, RoundStatus.clarifying)
        await db.flush()

        if self.ai:
            requirement = self._build_requirement(story, round_)
            context = self._build_context(project, round_)
            asyncio.create_task(self._run_clarify_background(
                story.id, round_.id, requirement, context,
            ))
        else:
            self._transition(round_, RoundStatus.planning)
            await db.flush()

        logger.info("Created story %s with round %s", story.id, round_.id)
        await db.refresh(story)
        return story

    async def answer_questions(
        self, db: AsyncSession, story_id: str, answers: dict[str, str],
    ) -> Round:
        """Record answers and trigger planning."""
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)

        for c in round_.clarifications:
            if c.id in answers:
                c.answer = answers[c.id]

        self._transition(round_, RoundStatus.planning)
        await db.flush()

        if self.ai:
            project = story.project
            requirement = self._build_requirement(story, round_)
            context = self._build_context(project, round_)
            asyncio.create_task(self._run_plan_background(
                story.id, round_.id, requirement, context,
            ))

        logger.info("Answered questions for round %s, now planning", round_.id)
        await db.refresh(round_)
        return round_

    async def generate_plan(
        self, db: AsyncSession, story_id: str,
    ) -> Round:
        """Generate (or regenerate) an implementation plan for the active round.

        The round must be in ``planning`` status.  Runs in the background.
        """
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)

        if round_.status != RoundStatus.planning:
            raise OrchestratorError(
                f"Cannot generate plan: round is in '{round_.status.value}' state"
            )

        if not self.ai:
            raise OrchestratorError("AI provider is not configured")

        project = story.project
        requirement = self._build_requirement(story, round_)
        context = self._build_context(project, round_)
        asyncio.create_task(self._run_plan_background(
            story.id, round_.id, requirement, context,
        ))

        logger.info("Triggered background plan generation for round %s", round_.id)
        await db.refresh(round_)
        return round_

    async def confirm_plan(
        self, db: AsyncSession, story_id: str,
        approved: bool, feedback: str | None = None,
    ) -> Round:
        """Confirm or reject the AI-generated plan."""
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)

        if not approved:
            if feedback:
                db.add(AIMessage(
                    round_id=round_.id, role=AIMessageRole.user,
                    content=f"[Plan Feedback] {feedback}",
                ))
                await db.flush()
            if self.ai:
                project = story.project
                requirement = self._build_requirement(story, round_)
                context = self._build_context(project, round_)
                if feedback:
                    context["plan_feedback"] = feedback
                asyncio.create_task(self._run_plan_background(
                    story.id, round_.id, requirement, context,
                    tag="[Revised Plan]",
                ))
            await db.refresh(round_)
            return round_

        self._transition(round_, RoundStatus.coding)
        await db.flush()

        if self.ai:
            project = story.project
            work_dir = self._work_dir(project, story)
            requirement = self._build_requirement(story, round_)
            context = self._build_context(project, round_)

            if self.scm and not (work_dir / ".git").exists():
                try:
                    await self.scm.clone_repo(project.repo_url, str(work_dir))
                except Exception:
                    logger.exception("Clone failed for story %s", story.id)

            branch_name = f"opd/{story.id[:8]}/round-{round_.round_number}"
            if self.scm and (work_dir / ".git").exists():
                try:
                    await self.scm.create_branch(str(work_dir), branch_name)
                    round_.branch_name = branch_name
                    await db.flush()
                except Exception:
                    logger.exception("Branch creation failed for round %s", round_.id)

            plan_data: dict[str, Any] = {}
            for msg in round_.ai_messages:
                if "[Implementation Plan]" in msg.content or "[Revised Plan]" in msg.content:
                    try:
                        plan_json = msg.content.split("\n", 1)[1] if "\n" in msg.content else "{}"
                        plan_data = json.loads(plan_json)
                    except (json.JSONDecodeError, IndexError):
                        pass

            round_id = round_.id

            def _code_factory():
                return self.ai.code(requirement, plan_data, context, work_dir=str(work_dir))

            asyncio.create_task(self._run_ai_background(
                "coding", story.id, round_id, _code_factory, RoundStatus.pr_created,
            ))

        logger.info("Plan confirmed for round %s, now coding", round_.id)
        await db.refresh(round_)
        return round_

    async def trigger_revision(
        self, db: AsyncSession, story_id: str,
        mode: str, prompt: str | None = None,
    ) -> Round:
        """Trigger a revision pass on the current round."""
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)
        self._transition(round_, RoundStatus.revising)

        feedback_text: str
        if mode == "comments" and self.scm and round_.pr_id:
            try:
                project = story.project
                repo_name = self._get_repo_name(project)
                comments = await self.scm.get_review_comments(repo_name, int(round_.pr_id))
                feedback_text = json.dumps(comments, indent=2, default=str)
            except Exception:
                logger.exception("Failed to fetch PR comments for round %s", round_.id)
                feedback_text = prompt or "(Failed to fetch PR comments)"
        else:
            feedback_text = prompt or ""

        db.add(AIMessage(
            round_id=round_.id, role=AIMessageRole.user,
            content=f"[Revision Request] {feedback_text}",
        ))
        await db.flush()

        if self.ai:
            project = story.project
            work_dir = self._work_dir(project, story)
            context = self._build_context(project, round_)
            feedback_list = [{"body": feedback_text}]
            round_id = round_.id

            def _revise_factory():
                return self.ai.revise(feedback_list, context, work_dir=str(work_dir))

            asyncio.create_task(self._run_ai_background(
                "revision", story.id, round_id, _revise_factory, RoundStatus.reviewing,
            ))

        logger.info("Triggered revision for round %s (mode=%s)", round_.id, mode)
        await db.refresh(round_)
        return round_

    async def new_round(
        self, db: AsyncSession, story_id: str, round_type: str,
        reason: str | None = None, new_requirement: str | None = None,
    ) -> Round:
        """Start a new round for a story."""
        story = await self._get_story(db, story_id)
        old_round = self._active_round(story)

        if old_round.status != RoundStatus.done:
            old_round.close_reason = reason or "New round started"
            old_round.status = RoundStatus.done

        next_number = old_round.round_number + 1
        story.current_round = next_number
        requirement_snapshot = new_requirement or story.requirement

        round_ = Round(
            story_id=story.id, round_number=next_number,
            type=RoundType(round_type), requirement_snapshot=requirement_snapshot,
            status=RoundStatus.created,
        )
        db.add(round_)
        await db.flush()
        self._transition(round_, RoundStatus.clarifying)
        await db.flush()

        if self.ai:
            project = story.project
            requirement = self._build_requirement(story, round_)
            context = self._build_context(project, round_)
            asyncio.create_task(self._run_clarify_background(
                story.id, round_.id, requirement, context,
            ))
        else:
            self._transition(round_, RoundStatus.planning)
            await db.flush()

        logger.info("Started new round %s (#%d) for story %s", round_.id, next_number, story.id)
        await db.refresh(round_)
        return round_

    async def trigger_test(self, db: AsyncSession, story_id: str) -> Round:
        """Trigger test execution for the current round."""
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)
        self._transition(round_, RoundStatus.testing)
        await db.flush()

        if self.ci and round_.branch_name:
            try:
                project = story.project
                repo_name = self._get_repo_name(project)
                result = await self.ci.trigger_pipeline(repo_name, round_.branch_name)
                db.add(AIMessage(
                    round_id=round_.id, role=AIMessageRole.tool,
                    content=f"[CI Pipeline] {json.dumps(result, default=str)}",
                ))
                await db.flush()
            except Exception:
                logger.exception("CI trigger failed for round %s", round_.id)

        logger.info("Triggered tests for round %s", round_.id)
        await db.refresh(round_)
        return round_

    async def merge(self, db: AsyncSession, story_id: str) -> Story:
        """Merge the PR and mark the story as done."""
        story = await self._get_story(db, story_id)
        round_ = self._active_round(story)

        if round_.status not in (
            RoundStatus.reviewing, RoundStatus.testing, RoundStatus.done,
        ):
            raise OrchestratorError(
                f"Cannot merge: round is in '{round_.status.value}' state"
            )

        if self.scm and round_.pr_id:
            try:
                project = story.project
                repo_name = self._get_repo_name(project)
                await self.scm.merge_pull_request(repo_name, int(round_.pr_id))
                round_.pr_status = PRStatus.merged
            except Exception:
                logger.exception("SCM merge failed for round %s", round_.id)

        if round_.status != RoundStatus.done:
            self._transition(round_, RoundStatus.done)

        story.status = StoryStatus.done
        await db.flush()
        logger.info("Merged story %s", story.id)
        await db.refresh(story)
        return story
