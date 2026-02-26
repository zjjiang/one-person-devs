"""Tests for project management API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.db.models import Base, Project, ProjectCapabilityConfig, WorkspaceStatus


@pytest.fixture
async def project_db():
    """In-memory DB with a seeded project."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        async with db.begin():
            p = Project(name="test-proj", repo_url="https://github.com/t/r",
                        description="desc", tech_stack="Python",
                        architecture="monolith",
                        workspace_status=WorkspaceStatus.ready)
            db.add(p)

    yield sf
    await engine.dispose()


# ── list_projects ──


class TestListProjects:
    async def test_list_empty(self):
        from opd.api.projects import list_projects

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as db:
            async with db.begin():
                result = await list_projects(db)
                assert result == []
        await engine.dispose()

    async def test_list_with_projects(self, project_db):
        from opd.api.projects import list_projects

        async with project_db() as db:
            async with db.begin():
                result = await list_projects(db)
                assert len(result) == 1
                assert result[0]["name"] == "test-proj"


# ── get_project ──


class TestGetProject:
    async def test_get_ok(self, project_db, orchestrator):
        from opd.api.projects import get_project

        async with project_db() as db:
            async with db.begin():
                result = await get_project(1, db, orchestrator)
                assert result["name"] == "test-proj"
                assert result["tech_stack"] == "Python"
                assert "rules" in result
                assert "stories" in result

    async def test_get_not_found(self, project_db, orchestrator):
        from fastapi import HTTPException
        from opd.api.projects import get_project

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await get_project(999, db, orchestrator)
                assert exc_info.value.status_code == 404


# ── create_project ──


class TestCreateProject:
    @patch("opd.api.projects._launch_clone")
    async def test_create_ok(self, mock_clone, project_db):
        from opd.api.projects import create_project
        from opd.models.schemas import CreateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = CreateProjectRequest(name="new", repo_url="https://github.com/n/r")
                result = await create_project(req, db)
                assert result["name"] == "new"
                mock_clone.assert_called_once()


# ── update_project ──


class TestUpdateProject:
    async def test_update_fields(self, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = UpdateProjectRequest(
                    name="updated", description="new desc", tech_stack="Go",
                )
                result = await update_project(1, req, db)
                assert result["name"] == "updated"
                assert result["workspace_reclone"] is False

    async def test_update_not_found(self, project_db):
        from fastapi import HTTPException
        from opd.api.projects import update_project
        from opd.models.schemas import UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await update_project(999, UpdateProjectRequest(name="x"), db)

    @patch("opd.api.projects._launch_clone")
    async def test_repo_url_change_triggers_reclone(self, mock_clone, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = UpdateProjectRequest(
                    name="test-proj",
                    repo_url="https://github.com/new/repo",
                )
                result = await update_project(1, req, db)
                assert result["workspace_reclone"] is True
                mock_clone.assert_called_once_with(1, "https://github.com/new/repo")

                # Verify project was updated
                proj_result = await db.execute(
                    select(Project).where(Project.id == 1)
                )
                proj = proj_result.scalar_one()
                assert proj.repo_url == "https://github.com/new/repo"
                assert proj.workspace_status == WorkspaceStatus.pending

    @patch("opd.api.projects._launch_clone")
    async def test_same_repo_url_no_reclone(self, mock_clone, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = UpdateProjectRequest(
                    name="test-proj",
                    repo_url="https://github.com/t/r",  # same as seeded
                )
                result = await update_project(1, req, db)
                assert result["workspace_reclone"] is False
                mock_clone.assert_not_called()

    async def test_capabilities_upsert(self, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import CapabilityToggle, UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = UpdateProjectRequest(
                    name="test-proj",
                    capabilities=[
                        CapabilityToggle(capability="ai", provider="claude_code", enabled=True),
                        CapabilityToggle(capability="scm", provider="github", enabled=False),
                    ],
                )
                await update_project(1, req, db)

                # Verify capabilities were created
                caps_result = await db.execute(
                    select(ProjectCapabilityConfig)
                    .where(ProjectCapabilityConfig.project_id == 1)
                )
                caps = caps_result.scalars().all()
                assert len(caps) == 2
                by_cap = {c.capability: c for c in caps}
                assert by_cap["ai"].enabled is True
                assert by_cap["scm"].enabled is False
                assert by_cap["ai"].provider_override == "claude_code"

    async def test_capabilities_update_existing(self, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import CapabilityToggle, UpdateProjectRequest

        async with project_db() as db:
            # First create a capability
            async with db.begin():
                db.add(ProjectCapabilityConfig(
                    project_id=1, capability="ai", enabled=True,
                    provider_override="old_provider",
                ))

            # Now update it
            async with db.begin():
                req = UpdateProjectRequest(
                    name="test-proj",
                    capabilities=[
                        CapabilityToggle(capability="ai", provider="ducc", enabled=False),
                    ],
                )
                await update_project(1, req, db)

                caps_result = await db.execute(
                    select(ProjectCapabilityConfig)
                    .where(ProjectCapabilityConfig.project_id == 1)
                )
                cap = caps_result.scalar_one()
                assert cap.enabled is False
                # provider_override should be updated
                assert cap.provider_override == "ducc"

    async def test_workspace_dir_update(self, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import UpdateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = UpdateProjectRequest(
                    name="test-proj",
                    workspace_dir="/new/path",
                )
                await update_project(1, req, db)

                proj_result = await db.execute(
                    select(Project).where(Project.id == 1)
                )
                proj = proj_result.scalar_one()
                assert proj.workspace_dir == "/new/path"


# ── init_workspace ──


class TestInitWorkspace:
    @patch("opd.api.projects._launch_clone")
    async def test_init_ok(self, mock_clone, project_db):
        from opd.api.projects import init_workspace

        async with project_db() as db:
            async with db.begin():
                result = await init_workspace(1, db)
                assert result["status"] == "cloning"
                mock_clone.assert_called_once()

    @patch("opd.api.projects._launch_clone")
    async def test_init_already_cloning(self, mock_clone, project_db):
        from opd.api.projects import init_workspace

        async with project_db() as db:
            async with db.begin():
                result = await db.execute(select(Project).where(Project.id == 1))
                proj = result.scalar_one()
                proj.workspace_status = WorkspaceStatus.cloning
        async with project_db() as db:
            async with db.begin():
                result = await init_workspace(1, db)
                assert "already" in result["message"].lower()
                mock_clone.assert_not_called()

    async def test_init_not_found(self, project_db):
        from fastapi import HTTPException
        from opd.api.projects import init_workspace

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await init_workspace(999, db)


# ── workspace_status ──


class TestWorkspaceStatus:
    async def test_status_ok(self, project_db):
        from opd.api.projects import workspace_status

        async with project_db() as db:
            async with db.begin():
                result = await workspace_status(1, db)
                assert result["status"] == "ready"

    async def test_status_not_found(self, project_db):
        from fastapi import HTTPException
        from opd.api.projects import workspace_status

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await workspace_status(999, db)


# ── _ai_incremental_update_claude_md ──


class TestIncrementalUpdateClaudeMd:
    async def test_returns_updated_content(self):
        from opd.api.projects import _ai_incremental_update_claude_md

        async def fake_plan(system, user, work_dir=""):
            yield {"type": "assistant", "content": "# Updated CLAUDE.md\nNew content"}

        ai_cap = MagicMock()
        ai_cap.provider.plan = fake_plan

        result = await _ai_incremental_update_claude_md(
            ai_cap, "diff summary", "# Old CLAUDE.md",
        )
        assert "Updated" in result

    async def test_returns_existing_on_empty_response(self):
        from opd.api.projects import _ai_incremental_update_claude_md

        async def fake_plan(system, user, work_dir=""):
            return
            yield  # noqa: make it an async generator

        ai_cap = MagicMock()
        ai_cap.provider.plan = fake_plan

        result = await _ai_incremental_update_claude_md(
            ai_cap, "diff", "# Existing",
        )
        assert result == "# Existing"


# ── UpdateProjectRequest schema ──


class TestUpdateProjectRequest:
    def test_valid(self):
        from opd.models.schemas import UpdateProjectRequest

        req = UpdateProjectRequest(name="proj", description="desc", tech_stack="Go")
        assert req.name == "proj"

    def test_defaults(self):
        from opd.models.schemas import UpdateProjectRequest

        req = UpdateProjectRequest(name="proj")
        assert req.description == ""
        assert req.tech_stack == ""
        assert req.architecture == ""

    def test_optional_fields(self):
        from opd.models.schemas import UpdateProjectRequest

        # repo_url, workspace_dir, capabilities are optional (None by default)
        req = UpdateProjectRequest(name="proj")
        assert req.repo_url is None
        assert req.workspace_dir is None
        assert req.capabilities is None
