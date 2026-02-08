"""FastAPI dependency injection helpers for OPD."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from opd.db.session import get_db
from opd.engine.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Orchestrator singleton
# ---------------------------------------------------------------------------

_orchestrator: Orchestrator | None = None


def init_orchestrator(providers: dict, workspace_dir: str = "./workspace") -> Orchestrator:
    """Create and store the global Orchestrator instance."""
    global _orchestrator
    _orchestrator = Orchestrator(providers=providers, workspace_dir=workspace_dir)
    return _orchestrator


def get_orchestrator() -> Orchestrator:
    """FastAPI dependency that returns the Orchestrator singleton.

    Raises
    ------
    RuntimeError
        If the orchestrator has not been initialised yet (i.e.
        :func:`init_orchestrator` was never called during startup).
    """
    if _orchestrator is None:
        raise RuntimeError(
            "Orchestrator not initialised. "
            "Call init_orchestrator() during app startup."
        )
    return _orchestrator


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Thin wrapper around :func:`opd.db.session.get_db`.

    Exists so that API routes have a single, consistent dependency name.
    """
    async for session in get_db():
        yield session
