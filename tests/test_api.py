"""Tests for API routes using in-memory SQLite."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.api.deps import get_db, get_orch
from opd.capabilities.base import Capability
from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import Base, StoryStatus
from opd.engine.orchestrator import Orchestrator
from opd.engine.stages.preparing import PreparingStage
from opd.engine.state_machine import StateMachine
from opd.main import create_app, get_orchestrator

from conftest import MockAIProvider


@pytest.fixture
async def app_client():
    """Create a test app with in-memory DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app()

    # Override DB dependency
    async def override_get_db():
        async with session_factory() as session:
            async with session.begin():
                yield session

    # Override orchestrator dependency
    registry = CapabilityRegistry()
    registry._capabilities["ai"] = Capability("ai", MockAIProvider())
    stages = {StoryStatus.preparing.value: PreparingStage()}
    orch = Orchestrator(stages=stages, state_machine=StateMachine(), capabilities=registry)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_orch] = lambda: orch
    app.dependency_overrides[get_orchestrator] = lambda: orch

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


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
