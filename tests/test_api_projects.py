"""Tests for project management API routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.db.models import Base, Project, WorkspaceStatus


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
    async def test_get_ok(self, project_db):
        from opd.api.projects import get_project

        async with project_db() as db:
            async with db.begin():
                result = await get_project(1, db)
                assert result["name"] == "test-proj"
                assert result["tech_stack"] == "Python"
                assert "rules" in result
                assert "stories" in result

    async def test_get_not_found(self, project_db):
        from fastapi import HTTPException
        from opd.api.projects import get_project

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException) as exc_info:
                    await get_project(999, db)
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
    @patch("opd.api.projects._launch_clone")
    async def test_update_same_url(self, mock_clone, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import CreateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = CreateProjectRequest(name="updated", repo_url="https://github.com/t/r")
                result = await update_project(1, req, db)
                assert result["name"] == "updated"
                mock_clone.assert_not_called()

    @patch("opd.api.projects._launch_clone")
    async def test_update_new_url_reclones(self, mock_clone, project_db):
        from opd.api.projects import update_project
        from opd.models.schemas import CreateProjectRequest

        async with project_db() as db:
            async with db.begin():
                req = CreateProjectRequest(name="updated", repo_url="https://github.com/new/r")
                await update_project(1, req, db)
                mock_clone.assert_called_once()

    async def test_update_not_found(self, project_db):
        from fastapi import HTTPException
        from opd.api.projects import update_project
        from opd.models.schemas import CreateProjectRequest

        async with project_db() as db:
            async with db.begin():
                with pytest.raises(HTTPException):
                    await update_project(999, CreateProjectRequest(
                        name="x", repo_url="https://github.com/t/r",
                    ), db)


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
