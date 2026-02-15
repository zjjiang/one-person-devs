"""Shared test fixtures for OPD v2."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opd.capabilities.base import Capability, HealthStatus, Provider
from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import Base, RoundStatus, RoundType, StoryStatus
from opd.engine.orchestrator import Orchestrator
from opd.engine.state_machine import StateMachine


# --- Mock Provider ---


class MockAIProvider(Provider):
    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, message="mock ok")

    async def prepare_prd(self, system_prompt, user_prompt):
        yield {"type": "assistant", "content": "Mock PRD content"}

    async def clarify(self, system_prompt, user_prompt):
        yield {"type": "assistant", "content": "No questions"}

    async def plan(self, system_prompt, user_prompt):
        yield {"type": "assistant", "content": "Mock plan"}

    async def design(self, system_prompt, user_prompt):
        yield {"type": "assistant", "content": "Mock design"}

    async def code(self, system_prompt, user_prompt):
        yield {"type": "assistant", "content": "Mock code"}


class UnhealthyProvider(Provider):
    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="connection refused")


# --- Fixtures ---


@pytest.fixture
def mock_project():
    return SimpleNamespace(
        id=1, name="test-project", repo_url="https://github.com/test/repo",
        description="Test project", tech_stack="Python", architecture="monolith",
    )


@pytest.fixture
def mock_story():
    return SimpleNamespace(
        id=1, project_id=1, title="Test story", raw_input="Build a login page",
        status=StoryStatus.preparing, current_round=1,
        prd=None, confirmed_prd=None, technical_design=None, detailed_design=None,
        feature_tag=None,
    )


@pytest.fixture
def mock_round():
    return SimpleNamespace(
        id=1, story_id=1, round_number=1, type=RoundType.initial,
        status=RoundStatus.active, branch_name="",
    )


@pytest.fixture
def state_machine():
    return StateMachine()


@pytest.fixture
def capability_registry():
    registry = CapabilityRegistry()
    ai_provider = MockAIProvider()
    registry._capabilities["ai"] = Capability("ai", ai_provider)
    return registry


@pytest.fixture
def orchestrator(capability_registry):
    from opd.engine.stages.preparing import PreparingStage
    stages = {StoryStatus.preparing.value: PreparingStage()}
    sm = StateMachine()
    return Orchestrator(stages=stages, state_machine=sm, capabilities=capability_registry)


@pytest.fixture
async def db_session():
    """In-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
    await engine.dispose()
