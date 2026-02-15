"""Async database session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory = None


def init_db(database_url: str):
    """Initialize the async engine and session factory."""
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session with auto-commit."""
    async with _session_factory() as session:
        async with session.begin():
            yield session


async def close_db():
    """Dispose the engine on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
