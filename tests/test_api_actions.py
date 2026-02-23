"""Tests for story action routes (rollback, iterate, restart, stop)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.db.models import (
    Base,
    Clarification,
    Project,
    Round,
    RoundStatus,
    Story,
    StoryStatus,
    Task,
    WorkspaceStatus,
)


@pytest.fixture
async def action_db():
    """In-memory DB with story in designing status."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        async with db.begin():
            p = Project(name="test", repo_url="https://github.com/t/r",
                        workspace_status=WorkspaceStatus.ready)
            db.add(p)
            await db.flush()
            s = Story(project_id=p.id, title="Test", raw_input="x",
                      status=StoryStatus.designing, current_round=1)
            db.add(s)
            await db.flush()
            r = Round(story_id=s.id, round_number=1, type="initial",
                      status=RoundStatus.active, branch_name="opd/story-1-r1")
            db.add(r)
            db.add(Task(story_id=s.id, title="task1", order=1))
            db.add(Clarification(story_id=s.id, question="Q?"))
            await db.flush()

    yield sf
    await engine.dispose()


# ── stop_story ──


class TestStopStory:
    async def test_stop_ok(self):
        from opd.api.stories_actions import stop_story

        orch = MagicMock()
        orch.stop_task.return_value = True
        result = await stop_story(1, orch)
        assert result["stopped"] is True

    async def test_stop_no_task(self):
        from opd.api.stories_actions import stop_story

        orch = MagicMock()
        orch.stop_task.return_value = False
        result = await stop_story(1, orch)
        assert result["stopped"] is False


# ── rollback_story ──


class TestRollbackStory:
    async def test_rollback_to_preparing(self, action_db):
        from opd.api.stories_actions import rollback_story
        from opd.models.schemas import RollbackRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                result = await rollback_story(
                    1, RollbackRequest(target_stage="preparing"), db, orch,
                )
                assert result["status"] == "preparing"

    async def test_rollback_clears_tasks(self, action_db):
        from opd.api.stories_actions import rollback_story
        from opd.models.schemas import RollbackRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                await rollback_story(
                    1, RollbackRequest(target_stage="clarifying"), db, orch,
                )
        # Verify tasks were deleted
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(select(Task).where(Task.story_id == 1))
                assert len(result.scalars().all()) == 0

    async def test_rollback_clears_clarifications(self, action_db):
        from opd.api.stories_actions import rollback_story
        from opd.models.schemas import RollbackRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                await rollback_story(
                    1, RollbackRequest(target_stage="preparing"), db, orch,
                )
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(
                    select(Clarification).where(Clarification.story_id == 1)
                )
                assert len(result.scalars().all()) == 0

    async def test_rollback_not_found(self, action_db):
        from fastapi import HTTPException
        from opd.api.stories_actions import rollback_story
        from opd.models.schemas import RollbackRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await rollback_story(
                        999, RollbackRequest(target_stage="preparing"), db, orch,
                    )
                assert exc_info.value.status_code == 404

    async def test_rollback_same_stage(self, action_db):
        from fastapi import HTTPException
        from opd.api.stories_actions import rollback_story
        from opd.models.schemas import RollbackRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await rollback_story(
                        1, RollbackRequest(target_stage="designing"), db, orch,
                    )
                assert exc_info.value.status_code == 400


# ── iterate_story ──


class TestIterateStory:
    @patch("opd.api.stories_actions._start_ai_stage")
    @patch("opd.api.stories_actions.delete_doc")
    async def test_iterate_ok(self, mock_del, mock_start, action_db):
        from opd.api.stories_actions import iterate_story
        from opd.models.schemas import IterateRequest

        orch = MagicMock()
        # Set story to verifying
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.verifying
        async with action_db() as db:
            async with db.begin():
                result = await iterate_story(
                    1, IterateRequest(feedback="Fix bugs"), db, orch,
                )
                assert result["action"] == "iterate"
                assert result["status"] == "coding"

    @patch("opd.api.stories_actions._start_ai_stage")
    @patch("opd.api.stories_actions.delete_doc")
    async def test_iterate_no_feedback(self, mock_del, mock_start, action_db):
        from opd.api.stories_actions import iterate_story

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.verifying
        async with action_db() as db:
            async with db.begin():
                result = await iterate_story(1, None, db, orch)
                assert result["action"] == "iterate"

    async def test_iterate_wrong_status(self, action_db):
        from opd.api.stories_actions import iterate_story

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                # designing status → raises HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await iterate_story(1, None, db, orch)
                assert exc_info.value.status_code == 400


# ── restart_story ──


class TestRestartStory:
    @patch("opd.api.stories_actions.discard_branch", new_callable=AsyncMock)
    @patch("opd.api.stories_actions.delete_doc")
    async def test_restart_ok(self, mock_del, mock_discard, action_db):
        from opd.api.stories_actions import restart_story
        from opd.models.schemas import IterateRequest

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.verifying
        async with action_db() as db:
            async with db.begin():
                result = await restart_story(
                    1, IterateRequest(feedback="Start over"), db, orch,
                )
                assert result["action"] == "restart"
                assert result["status"] == "designing"
                mock_discard.assert_called_once()

    @patch("opd.api.stories_actions.discard_branch", new_callable=AsyncMock,
           side_effect=RuntimeError("git error"))
    @patch("opd.api.stories_actions.delete_doc")
    async def test_restart_discard_fails_gracefully(self, mock_del, mock_discard, action_db):
        from opd.api.stories_actions import restart_story

        orch = MagicMock()
        async with action_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.verifying
        async with action_db() as db:
            async with db.begin():
                result = await restart_story(1, None, db, orch)
                assert result["action"] == "restart"  # should not crash
