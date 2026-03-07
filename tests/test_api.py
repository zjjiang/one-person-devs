"""Tests for API routes using in-memory SQLite."""

from pathlib import Path
from unittest.mock import patch

import pytest

from opd.db.models import Project, WorkspaceStatus


class TestProjectAPI:
    async def test_create_project(self, app_client):
        resp = await app_client.post("/api/projects", json={
            "name": "test-proj", "repo_url": "https://github.com/t/r",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-proj"
        assert "id" in data

    async def test_list_projects(self, app_client):
        await app_client.post("/api/projects", json={
            "name": "proj1", "repo_url": "https://github.com/t/r1",
        })
        resp = await app_client.get("/api/projects")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_get_project(self, app_client):
        create = await app_client.post("/api/projects", json={
            "name": "proj2", "repo_url": "https://github.com/t/r2",
        })
        pid = create.json()["id"]
        resp = await app_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "proj2"


class TestStoryAPI:
    async def _create_project(self, client):
        resp = await client.post("/api/projects", json={
            "name": "sp", "repo_url": "https://github.com/t/r",
        })
        return resp.json()["id"]

    async def test_create_story_blocked_by_workspace(self, app_client):
        """Story creation requires workspace ready + CLAUDE.md."""
        pid = await self._create_project(app_client)
        resp = await app_client.post(f"/api/projects/{pid}/stories", json={
            "title": "Login page", "raw_input": "Build a login page",
        })
        assert resp.status_code == 400
        assert "工作区未就绪" in resp.json()["detail"]

    async def test_create_story_blocked_by_claude_md(self, app_client, tmp_path):
        """Story creation blocked when CLAUDE.md missing even if workspace ready."""
        pid = await self._create_project(app_client)
        # No CLAUDE.md in tmp_path
        with patch("opd.api.stories.resolve_work_dir", return_value=tmp_path):
            # Also need to patch workspace_status — set it via DB
            from opd.api.deps import get_db

            async for db in app_client._transport.app.dependency_overrides[get_db]():
                project = await db.get(Project, pid)
                project.workspace_status = WorkspaceStatus.ready

            resp = await app_client.post(f"/api/projects/{pid}/stories", json={
                "title": "Login page", "raw_input": "Build a login page",
            })
        assert resp.status_code == 400
        assert "CLAUDE.md" in resp.json()["detail"]

    async def test_create_story(self, app_client, tmp_path):
        """Story creation succeeds with ready workspace and CLAUDE.md."""
        pid = await self._create_project(app_client)

        # Set workspace to ready
        from opd.api.deps import get_db

        async for db in app_client._transport.app.dependency_overrides[get_db]():
            project = await db.get(Project, pid)
            project.workspace_status = WorkspaceStatus.ready

        # Create CLAUDE.md
        (tmp_path / "CLAUDE.md").write_text("# Test")

        with patch("opd.api.stories.resolve_work_dir", return_value=tmp_path):
            resp = await app_client.post(f"/api/projects/{pid}/stories", json={
                "title": "Login page", "raw_input": "Build a login page",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "preparing"

    async def test_get_story(self, app_client, tmp_path):
        pid = await self._create_project(app_client)

        from opd.api.deps import get_db

        async for db in app_client._transport.app.dependency_overrides[get_db]():
            project = await db.get(Project, pid)
            project.workspace_status = WorkspaceStatus.ready

        (tmp_path / "CLAUDE.md").write_text("# Test")

        with patch("opd.api.stories.resolve_work_dir", return_value=tmp_path):
            create = await app_client.post(f"/api/projects/{pid}/stories", json={
                "title": "Test", "raw_input": "Test input",
            })
        sid = create.json()["id"]
        resp = await app_client.get(f"/api/stories/{sid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test"

    async def test_confirm_stage(self, app_client, tmp_path):
        pid = await self._create_project(app_client)

        from opd.api.deps import get_db

        async for db in app_client._transport.app.dependency_overrides[get_db]():
            project = await db.get(Project, pid)
            project.workspace_status = WorkspaceStatus.ready

        (tmp_path / "CLAUDE.md").write_text("# Test")

        with patch("opd.api.stories.resolve_work_dir", return_value=tmp_path):
            create = await app_client.post(f"/api/projects/{pid}/stories", json={
                "title": "Confirm test", "raw_input": "input",
            })
        sid = create.json()["id"]
        resp = await app_client.post(f"/api/stories/{sid}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "clarifying"

    async def test_health_endpoint(self, app_client):
        resp = await app_client.get("/api/health")
        assert resp.status_code == 200
        assert "status" in resp.json()
