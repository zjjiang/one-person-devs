"""Dependency injection for API routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from opd.db.session import get_session
from opd.engine.orchestrator import Orchestrator
from opd.main import get_orchestrator


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_orch() -> Orchestrator:
    return get_orchestrator()
