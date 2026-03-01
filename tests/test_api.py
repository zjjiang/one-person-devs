"""Tests for API routes using in-memory SQLite."""

import pytest


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

    async def test_create_story(self, app_client):
        pid = await self._create_project(app_client)
        resp = await app_client.post(f"/api/projects/{pid}/stories", json={
            "title": "Login page", "raw_input": "Build a login page",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "preparing"

    async def test_get_story(self, app_client):
        pid = await self._create_project(app_client)
        create = await app_client.post(f"/api/projects/{pid}/stories", json={
            "title": "Test", "raw_input": "Test input",
        })
        sid = create.json()["id"]
        resp = await app_client.get(f"/api/stories/{sid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test"

    async def test_confirm_stage(self, app_client):
        pid = await self._create_project(app_client)
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
