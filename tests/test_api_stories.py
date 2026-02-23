"""Tests for story lifecycle API routes (stories.py, stories_docs.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
    WorkspaceStatus,
)


@pytest.fixture
async def story_db():
    """In-memory DB with a seeded project + story + round."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    # Seed data
    async with sf() as db:
        async with db.begin():
            p = Project(name="test", repo_url="https://github.com/t/r",
                        workspace_status=WorkspaceStatus.ready)
            db.add(p)
            await db.flush()
            s = Story(project_id=p.id, title="Test Story", raw_input="Build login",
                      status=StoryStatus.preparing, current_round=1)
            db.add(s)
            await db.flush()
            r = Round(story_id=s.id, round_number=1, type="initial",
                      status=RoundStatus.active)
            db.add(r)
            await db.flush()

    yield sf
    await engine.dispose()


# ── create_story ──


class TestCreateStory:
    @patch("opd.api.stories._start_ai_stage")
    async def test_create_ok(self, mock_start, story_db):
        from opd.api.stories import create_story
        from opd.models.schemas import CreateStoryRequest

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                req = CreateStoryRequest(title="Login", raw_input="Build login page")
                result = await create_story(1, req, db, orch)
                assert result["status"] == "preparing"
                assert result["id"] is not None
                mock_start.assert_called_once()


# ── get_story ──


class TestGetStory:
    async def test_get_ok(self, story_db):
        from opd.api.stories import get_story

        orch = MagicMock()
        orch.is_task_running.return_value = False
        async with story_db() as db:
            async with db.begin():
                result = await get_story(1, db, orch)
                assert result["title"] == "Test Story"
                assert result["status"] == "preparing"
                assert "rounds" in result
                assert "clarifications" in result

    async def test_get_not_found(self, story_db):
        from fastapi import HTTPException
        from opd.api.stories import get_story

        orch = MagicMock()
        orch.is_task_running.return_value = False
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await get_story(999, db, orch)
                assert exc_info.value.status_code == 404


# ── confirm_stage ──


class TestConfirmStage:
    @patch("opd.api.stories._start_ai_stage")
    async def test_confirm_preparing(self, mock_start, story_db):
        from opd.api.stories import confirm_stage

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                result = await confirm_stage(1, db, orch)
                assert result["status"] == "clarifying"

    @patch("opd.api.stories._start_ai_stage")
    async def test_confirm_not_found(self, mock_start, story_db):
        from opd.api.stories import confirm_stage

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await confirm_stage(999, db, orch)
                assert exc_info.value.status_code == 404

    @patch("opd.api.stories._start_ai_stage")
    @patch("opd.api.stories.should_skip_ai", return_value=True)
    async def test_confirm_skips_ai_when_unchanged(self, mock_skip, mock_start, story_db):
        from opd.api.stories import confirm_stage

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                result = await confirm_stage(1, db, orch)
                assert result["skipped_ai"] is True
                mock_start.assert_not_called()

    @patch("opd.api.stories._start_ai_stage")
    async def test_confirm_invalid_status(self, mock_start, story_db):
        from opd.api.stories import confirm_stage

        orch = MagicMock()
        # Set story to coding status (can't confirm)
        async with story_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.coding
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await confirm_stage(1, db, orch)
                assert exc_info.value.status_code == 400
                assert "coding" in str(exc_info.value.detail)


# ── reject_stage ──


class TestRejectStage:
    @patch("opd.api.stories._start_ai_stage")
    async def test_reject_ok(self, mock_start, story_db):
        from opd.api.stories import reject_stage

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                result = await reject_stage(1, db, orch)
                assert result["message"] == "Stage re-triggered"
                mock_start.assert_called_once()

    @patch("opd.api.stories._start_ai_stage")
    async def test_reject_not_found(self, mock_start, story_db):
        from opd.api.stories import reject_stage

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await reject_stage(999, db, orch)
                assert exc_info.value.status_code == 404


# ── update_prd ──


class TestUpdatePrd:
    @patch("opd.api.stories.write_doc", return_value="docs/stories/1/prd.md")
    async def test_update_ok(self, mock_write, story_db):
        from opd.api.stories import update_prd
        from opd.models.schemas import UpdatePrdRequest

        async with story_db() as db:
            async with db.begin():
                req = UpdatePrdRequest(prd="# Updated PRD")
                result = await update_prd(1, req, db)
                assert result["prd"] == "docs/stories/1/prd.md"

    async def test_update_not_found(self, story_db):
        from fastapi import HTTPException
        from opd.api.stories import update_prd
        from opd.models.schemas import UpdatePrdRequest

        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await update_prd(999, UpdatePrdRequest(prd="x"), db)
                assert exc_info.value.status_code == 404

    @patch("opd.api.stories.write_doc", return_value="docs/stories/1/prd.md")
    async def test_update_wrong_stage(self, mock_write, story_db):
        from fastapi import HTTPException
        from opd.api.stories import update_prd
        from opd.models.schemas import UpdatePrdRequest

        async with story_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.coding
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await update_prd(1, UpdatePrdRequest(prd="x"), db)
                assert exc_info.value.status_code == 400


# ── chat_message ──


class TestChatMessage:
    @patch("opd.api.stories._start_chat_ai")
    async def test_chat_ok(self, mock_chat, story_db):
        from opd.api.stories import chat_message
        from opd.models.schemas import ChatRequest

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                result = await chat_message(1, ChatRequest(message="Add auth"), db, orch)
                assert result["status"] == "processing"
                mock_chat.assert_called_once()

    @patch("opd.api.stories._start_chat_ai")
    async def test_chat_not_found(self, mock_chat, story_db):
        from opd.api.stories import chat_message
        from opd.models.schemas import ChatRequest

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await chat_message(999, ChatRequest(message="x"), db, orch)
                assert exc_info.value.status_code == 404

    @patch("opd.api.stories._start_chat_ai")
    async def test_chat_wrong_stage(self, mock_chat, story_db):
        from opd.api.stories import chat_message
        from opd.models.schemas import ChatRequest

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                result = await db.execute(select(Story).where(Story.id == 1))
                story = result.scalar_one()
                story.status = StoryStatus.coding
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await chat_message(1, ChatRequest(message="x"), db, orch)
                assert exc_info.value.status_code == 400


# ── answer_questions ──


class TestAnswerQuestions:
    @patch("opd.api.stories._start_chat_ai")
    async def test_answer_by_id(self, mock_chat, story_db):
        from opd.api.stories import answer_questions
        from opd.models.schemas import AnswerRequest, QAPair

        orch = MagicMock()
        # Add a clarification
        async with story_db() as db:
            async with db.begin():
                db.add(Clarification(story_id=1, question="What DB?"))
        async with story_db() as db:
            async with db.begin():
                req = AnswerRequest(answers=[QAPair(id=1, question="What DB?", answer="PG")])
                result = await answer_questions(1, req, db, orch)
                assert result["message"] == "Answers recorded"

    @patch("opd.api.stories._start_chat_ai")
    async def test_answer_by_question(self, mock_chat, story_db):
        from opd.api.stories import answer_questions
        from opd.models.schemas import AnswerRequest, QAPair

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                db.add(Clarification(story_id=1, question="Auth method?"))
        async with story_db() as db:
            async with db.begin():
                req = AnswerRequest(answers=[
                    QAPair(question="Auth method?", answer="JWT"),
                ])
                result = await answer_questions(1, req, db, orch)
                assert result["count"] >= 1


# ── preflight_check ──


class TestPreflightCheck:
    async def test_preflight_ok(self, story_db):
        from opd.api.stories import preflight_check
        from opd.capabilities.base import Capability
        from opd.capabilities.registry import CapabilityRegistry
        from opd.engine.orchestrator import Orchestrator
        from opd.engine.stages.preparing import PreparingStage
        from opd.engine.state_machine import StateMachine

        from conftest import MockAIProvider

        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", MockAIProvider())
        stages = {StoryStatus.preparing.value: PreparingStage()}
        orch = Orchestrator(stages=stages, state_machine=StateMachine(),
                            capabilities=registry)
        async with story_db() as db:
            async with db.begin():
                result = await preflight_check(1, db, orch)
                assert "ok" in result

    async def test_preflight_not_found(self, story_db):
        from opd.api.stories import preflight_check

        orch = MagicMock()
        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await preflight_check(999, db, orch)
                assert exc_info.value.status_code == 404


# ── stories_docs ──


class TestStoryDocs:
    @patch("opd.api.stories_docs.list_docs", return_value=["prd.md", "design.md"])
    async def test_list_docs(self, mock_list, story_db):
        from opd.api.stories_docs import list_story_docs

        async with story_db() as db:
            async with db.begin():
                result = await list_story_docs(1, db)
                assert result["files"] == ["prd.md", "design.md"]

    async def test_list_docs_not_found(self, story_db):
        from fastapi import HTTPException
        from opd.api.stories_docs import list_story_docs

        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await list_story_docs(999, db)

    @patch("opd.api.stories_docs.read_doc", return_value="# PRD content")
    async def test_get_doc(self, mock_read, story_db):
        from opd.api.stories_docs import get_story_doc

        async with story_db() as db:
            async with db.begin():
                result = await get_story_doc(1, "prd.md", db)
                assert result["content"] == "# PRD content"

    @patch("opd.api.stories_docs.read_doc", return_value=None)
    async def test_get_doc_not_found(self, mock_read, story_db):
        from fastapi import HTTPException
        from opd.api.stories_docs import get_story_doc

        async with story_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await get_story_doc(1, "missing.md", db)

    @patch("opd.api.stories_docs.write_doc", return_value="docs/stories/1/prd.md")
    async def test_save_doc(self, mock_write, story_db):
        from opd.api.stories_docs import save_story_doc
        from opd.models.schemas import UpdateDocRequest

        async with story_db() as db:
            async with db.begin():
                result = await save_story_doc(1, "prd.md", UpdateDocRequest(content="# New"), db)
                assert result["filename"] == "prd.md"
                assert result["path"] == "docs/stories/1/prd.md"

    @patch("opd.api.stories_docs.write_doc", return_value="docs/stories/1/custom.md")
    async def test_save_doc_unknown_field(self, mock_write, story_db):
        from opd.api.stories_docs import save_story_doc
        from opd.models.schemas import UpdateDocRequest

        async with story_db() as db:
            async with db.begin():
                result = await save_story_doc(1, "custom.md", UpdateDocRequest(content="x"), db)
                assert result["filename"] == "custom.md"
