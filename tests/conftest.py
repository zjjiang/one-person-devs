"""Shared fixtures for OPD tests.

Provides mock objects for Project, Story, Round, Rule, and Clarification
that can be reused across unit and integration tests without requiring
a real database connection.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from opd.db.models import (
    RoundStatus,
    RoundType,
    RuleCategory,
    StoryStatus,
)
from opd.main import create_app


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _make_project(**overrides):
    """Create a mock Project with sensible defaults."""
    defaults = dict(
        id="proj-001",
        name="Test Project",
        repo_url="https://github.com/test/repo",
        description="A test project for unit tests",
        tech_stack="Python, FastAPI, SQLAlchemy",
        architecture="Layered architecture with API, engine, and DB layers",
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
        rules=[],
        skills=[],
        stories=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_rule(**overrides):
    """Create a mock Rule with sensible defaults."""
    defaults = dict(
        id="rule-001",
        project_id="proj-001",
        category=RuleCategory.coding,
        content="Use type hints on all public functions",
        enabled=True,
        created_at=datetime(2025, 1, 1),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_story(**overrides):
    """Create a mock Story with sensible defaults."""
    defaults = dict(
        id="story-001",
        project_id="proj-001",
        title="Implement login endpoint",
        requirement="Add a POST /login endpoint that accepts email and password",
        requirement_source=None,
        requirement_id=None,
        acceptance_criteria="Returns JWT token on success, 401 on failure",
        status=StoryStatus.in_progress,
        current_round=1,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
        project=None,
        rounds=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_round(**overrides):
    """Create a mock Round with sensible defaults."""
    defaults = dict(
        id="round-001",
        story_id="story-001",
        round_number=1,
        type=RoundType.initial,
        requirement_snapshot="Add a POST /login endpoint",
        branch_name=None,
        pr_id=None,
        pr_status=None,
        close_reason=None,
        status=RoundStatus.created,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
        clarifications=[],
        ai_messages=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_clarification(**overrides):
    """Create a mock Clarification with sensible defaults."""
    defaults = dict(
        id="clar-001",
        round_id="round-001",
        question="Should the endpoint support OAuth?",
        answer=None,
        created_at=datetime(2025, 1, 1),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_project():
    """A mock Project instance."""
    return _make_project()


@pytest.fixture
def mock_rules():
    """A list of mock Rule instances with mixed enabled/disabled."""
    return [
        _make_rule(
            id="rule-001",
            category=RuleCategory.coding,
            content="Use type hints on all public functions",
            enabled=True,
        ),
        _make_rule(
            id="rule-002",
            category=RuleCategory.testing,
            content="Maintain 80% code coverage",
            enabled=True,
        ),
        _make_rule(
            id="rule-003",
            category=RuleCategory.forbidden,
            content="Do not use eval()",
            enabled=False,
        ),
    ]


@pytest.fixture
def mock_story():
    """A mock Story instance."""
    return _make_story()


@pytest.fixture
def mock_round():
    """A mock Round instance in 'created' status."""
    return _make_round()


@pytest.fixture
def mock_clarifications():
    """A list of mock Clarification instances."""
    return [
        _make_clarification(
            id="clar-001",
            question="Should the endpoint support OAuth?",
            answer="Yes, support Google OAuth",
        ),
        _make_clarification(
            id="clar-002",
            question="What token expiry time?",
            answer=None,
        ),
    ]


@pytest.fixture
def mock_round_with_clarifications(mock_round, mock_clarifications):
    """A mock Round that has clarifications attached."""
    mock_round.clarifications = mock_clarifications
    return mock_round


# ---------------------------------------------------------------------------
# Test client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """FastAPI test client for synchronous tests."""
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client():
    """FastAPI async test client for async tests."""
    from httpx import AsyncClient

    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
