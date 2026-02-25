"""Tests for notification system: model, API, and service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi import FastAPI
from opd.api.notifications import router as notifications_router
from opd.db.models import Base, Notification, NotificationType, ProjectCapabilityConfig


# --- Fixtures ---


@pytest.fixture
async def notification_db():
    """In-memory SQLite session factory for notification tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def seeded_db(notification_db):
    """Seed some notifications and return the factory."""
    async with notification_db() as db:
        async with db.begin():
            db.add(Notification(
                type=NotificationType.stage_completed,
                title="Stage done", message="coding ok",
                link="/projects/1/stories/1", story_id=1, project_id=1,
            ))
            db.add(Notification(
                type=NotificationType.stage_failed,
                title="Stage failed", message="error",
                link="/projects/1/stories/2", story_id=2, project_id=1,
                read=True,
            ))
    return notification_db


@pytest.fixture
async def api_client(seeded_db):
    """Test client with notification router + real DB."""
    app = FastAPI()
    app.include_router(notifications_router)

    # Override get_db to use our in-memory DB
    from opd.api import deps

    async def _override_db():
        async with seeded_db() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[deps.get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- Model Tests ---


class TestNotificationModel:
    async def test_create_notification(self, notification_db):
        async with notification_db() as db:
            async with db.begin():
                n = Notification(
                    type=NotificationType.pr_created,
                    title="PR created", message="PR #42",
                    link="/projects/1/stories/1",
                )
                db.add(n)
            async with db.begin():
                result = await db.execute(select(Notification))
                rows = result.scalars().all()
                assert len(rows) == 1
                assert rows[0].title == "PR created"
                assert rows[0].read is False

    async def test_notification_types(self):
        assert NotificationType.stage_completed.value == "stage_completed"
        assert NotificationType.stage_failed.value == "stage_failed"
        assert NotificationType.pr_created.value == "pr_created"


# --- API Tests ---


class TestNotificationAPI:
    async def test_list_all(self, api_client):
        resp = await api_client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_unread_only(self, api_client):
        resp = await api_client.get("/api/notifications?unread_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Stage done"

    async def test_unread_count(self, api_client):
        resp = await api_client.get("/api/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    async def test_mark_read(self, api_client):
        # Get the unread notification id
        resp = await api_client.get("/api/notifications?unread_only=true")
        nid = resp.json()[0]["id"]
        # Mark it read
        resp = await api_client.post(f"/api/notifications/{nid}/read")
        assert resp.status_code == 200
        # Verify count is now 0
        resp = await api_client.get("/api/notifications/unread-count")
        assert resp.json()["count"] == 0

    async def test_read_all(self, api_client):
        resp = await api_client.post("/api/notifications/read-all")
        assert resp.status_code == 200
        resp = await api_client.get("/api/notifications/unread-count")
        assert resp.json()["count"] == 0


# --- Service Layer Tests ---


class TestSendNotification:
    async def test_skips_when_project_has_no_notification_capability(self, notification_db):
        """send_notification does nothing if project hasn't enabled notification."""
        from opd.engine.notify import send_notification

        mock_registry = MagicMock()

        await send_notification(
            notification_db,
            NotificationType.stage_completed,
            "Test title", "Test message", "/link",
            mock_registry,
            story_id=1, project_id=1,
        )

        # No notification should be written
        async with notification_db() as db:
            async with db.begin():
                result = await db.execute(select(Notification))
                rows = result.scalars().all()
                assert len(rows) == 0

    async def test_inbox_writes_when_project_enabled(self, notification_db):
        """send_notification creates inbox DB record when project has notification enabled."""
        from opd.engine.notify import send_notification

        # Enable notification capability for project 1
        async with notification_db() as db:
            async with db.begin():
                db.add(ProjectCapabilityConfig(
                    project_id=1, capability="notification", enabled=True,
                ))

        mock_registry = MagicMock()

        await send_notification(
            notification_db,
            NotificationType.stage_completed,
            "Test title", "Test message", "/link",
            mock_registry,
            story_id=1, project_id=1,
        )

        async with notification_db() as db:
            async with db.begin():
                result = await db.execute(select(Notification))
                rows = result.scalars().all()
                assert len(rows) == 1
                assert rows[0].title == "Test title"
                assert rows[0].story_id == 1

    async def test_external_provider_called(self, notification_db):
        """send_notification calls external provider's send()."""
        from opd.engine.notify import send_notification

        # Enable notification capability for project 1 + seed feishu config
        from opd.db.models import GlobalCapabilityConfig
        async with notification_db() as db:
            async with db.begin():
                db.add(ProjectCapabilityConfig(
                    project_id=1, capability="notification", enabled=True,
                ))
                db.add(GlobalCapabilityConfig(
                    capability="notification", provider="feishu",
                    enabled=True, config={"app_id": "x", "app_secret": "y",
                                          "receive_id": "z"},
                ))

        mock_prov = AsyncMock()
        mock_prov.send = AsyncMock(return_value=True)
        mock_prov.initialize = AsyncMock()
        mock_prov.cleanup = AsyncMock()

        mock_registry = MagicMock()
        mock_registry.create_temp_provider = MagicMock(return_value=mock_prov)

        await send_notification(
            notification_db,
            NotificationType.stage_completed,
            "Test", "msg", "/link",
            mock_registry,
            story_id=1, project_id=1,
        )

        mock_prov.send.assert_called_once_with("Test", "msg", "/link")
