"""Database connection and session management."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opd.config import OPDConfig

# Global engine and session maker
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine.

    Returns:
        AsyncEngine instance

    Raises:
        RuntimeError: If engine is not initialized
    """
    global _engine
    if _engine is None:
        config = OPDConfig.load()
        _engine = create_async_engine(
            config.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the session maker.

    Returns:
        async_sessionmaker instance

    Raises:
        RuntimeError: If session maker is not initialized
    """
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session.

    Yields:
        AsyncSession instance

    Example:
        ```python
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
        ```
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables.

    Creates all tables defined in models if they don't exist.
    """
    from opd.models.base import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections and cleanup resources."""
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None

    _async_session_maker = None
