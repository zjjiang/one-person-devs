"""Abstract base class for requirement providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class RequirementProvider(Provider):
    """Interface for fetching and managing requirements.

    A *requirement* is represented as a plain ``dict`` with at least the
    following keys:

    - ``id`` -- unique identifier (string)
    - ``title`` -- short human-readable summary
    - ``description`` -- full markdown body
    - ``status`` -- workflow status (e.g. ``open``, ``in_progress``, ``done``)
    """

    @abstractmethod
    async def get_requirement(self, requirement_id: str) -> dict[str, Any]:
        """Return a single requirement by its *requirement_id*.

        Raises ``KeyError`` when the requirement does not exist.
        """

    @abstractmethod
    async def list_requirements(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Return requirements matching the optional *filters*.

        When *filters* is ``None`` or empty, all requirements are
        returned.  Supported filter keys are provider-specific.
        """

    @abstractmethod
    async def update_status(self, requirement_id: str, status: str) -> None:
        """Update the workflow status of a requirement."""
