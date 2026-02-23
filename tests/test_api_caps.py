"""Tests for capabilities and settings API routes."""

from __future__ import annotations


import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.capabilities.base import Capability
from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import (
    Base,
    GlobalCapabilityConfig,
    Project,
    ProjectCapabilityConfig,
    WorkspaceStatus,
)
from opd.engine.orchestrator import Orchestrator
from opd.engine.state_machine import StateMachine

from conftest import MockAIProvider


@pytest.fixture
async def cap_db():
    """In-memory DB with project and capability configs."""
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
            db.add(ProjectCapabilityConfig(
                project_id=p.id, capability="ai", enabled=True,
                provider_override="claude_code",
                config_override={"api_key": "sk-test"},
            ))

    yield sf
    await engine.dispose()


def _make_orch():
    """Create an orchestrator with mock AI provider."""
    registry = CapabilityRegistry()
    registry._capabilities["ai"] = Capability("ai", MockAIProvider())
    sm = StateMachine()
    return Orchestrator(stages={}, state_machine=sm, capabilities=registry)


# ── get_capabilities ──


class TestGetCapabilities:
    async def test_get_caps(self, cap_db):
        from opd.api.capabilities import get_capabilities

        orch = _make_orch()
        async with cap_db() as db:
            async with db.begin():
                result = await get_capabilities(1, orch, db)
                assert isinstance(result, list)
                assert len(result) >= 1
                ai_cap = next(c for c in result if c["capability"] == "ai")
                assert ai_cap["saved"]["enabled"] is True


# ── save_capability_config ──


class TestSaveCapabilityConfig:
    async def test_save_new(self, cap_db):
        from opd.api.capabilities import save_capability_config
        from opd.models.schemas import SaveCapabilityConfigRequest

        orch = _make_orch()
        async with cap_db() as db:
            req = SaveCapabilityConfigRequest(
                enabled=True, provider_override="ducc",
                config_override={"model": "test"},
            )
            result = await save_capability_config(1, "doc", req, orch, db)
            assert result["ok"] is True

    async def test_save_update_existing(self, cap_db):
        from opd.api.capabilities import save_capability_config
        from opd.models.schemas import SaveCapabilityConfigRequest

        orch = _make_orch()
        async with cap_db() as db:
            req = SaveCapabilityConfigRequest(
                enabled=False, provider_override="ducc",
                config_override={"model": "new"},
            )
            result = await save_capability_config(1, "ai", req, orch, db)
            assert result["ok"] is True


# ── batch_save_capabilities ──


class TestBatchSave:
    async def test_batch_ok(self, cap_db):
        from opd.api.capabilities import batch_save_capabilities
        from opd.models.schemas import SaveCapabilityConfigRequest

        async with cap_db() as db:
            body = [
                SaveCapabilityConfigRequest(
                    capability="ai", enabled=True,
                    provider_override="claude_code",
                ),
                SaveCapabilityConfigRequest(
                    capability="scm", enabled=True,
                    provider_override="github",
                    config_override={"token": "ghp_xxx"},
                ),
                SaveCapabilityConfigRequest(capability=""),  # empty, should skip
            ]
            result = await batch_save_capabilities(1, body, db)
            assert result["ok"] is True


# ── get_catalog ──


class TestGetCatalog:
    async def test_catalog(self):
        from opd.api.capabilities import get_catalog

        orch = _make_orch()
        result = await get_catalog(orch)
        assert isinstance(result, list)
        assert any(c["capability"] == "ai" for c in result)


# ── settings: get_global_capabilities ──


class TestGetGlobalCapabilities:
    async def test_get_global(self, cap_db):
        from opd.api.settings import get_global_capabilities

        orch = _make_orch()
        # Add a global config
        async with cap_db() as db:
            async with db.begin():
                db.add(GlobalCapabilityConfig(
                    capability="ai", enabled=True, provider="claude_code",
                    config={"api_key": "sk-global"},
                ))
        async with cap_db() as db:
            async with db.begin():
                result = await get_global_capabilities(orch, db)
                assert isinstance(result, list)
                ai_cap = next(c for c in result if c["capability"] == "ai")
                assert ai_cap["saved"]["enabled"] is True


# ── settings: save_global_capability ──


class TestSaveGlobalCapability:
    async def test_save_new(self, cap_db):
        from opd.api.settings import save_global_capability
        from opd.models.schemas import SaveCapabilityConfigRequest

        orch = _make_orch()
        async with cap_db() as db:
            req = SaveCapabilityConfigRequest(
                enabled=True, provider_override="claude_code",
                config_override={"api_key": "sk-new"},
            )
            result = await save_global_capability("ai", req, orch, db)
            assert result["ok"] is True

    async def test_save_update(self, cap_db):
        from opd.api.settings import save_global_capability
        from opd.models.schemas import SaveCapabilityConfigRequest

        orch = _make_orch()
        # Create initial
        async with cap_db() as db:
            async with db.begin():
                db.add(GlobalCapabilityConfig(
                    capability="scm", enabled=True, provider="github",
                    config={"token": "old"},
                ))
        async with cap_db() as db:
            req = SaveCapabilityConfigRequest(
                enabled=False, provider_override="github",
                config_override={"token": "new"},
            )
            result = await save_global_capability("scm", req, orch, db)
            assert result["ok"] is True
