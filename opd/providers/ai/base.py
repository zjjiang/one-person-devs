"""Abstract base class for AI coding providers."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from opd.providers.base import Provider


class AIProvider(Provider):
    """Interface for AI-powered coding assistance.

    Each method corresponds to a distinct phase of the AI coding
    workflow:

    1. **clarify** -- ask clarifying questions about a requirement.
    2. **plan** -- produce an implementation plan.
    3. **code** -- generate / apply code changes (streaming).
    4. **revise** -- revise code based on review feedback (streaming).
    """

    @abstractmethod
    async def clarify(
        self,
        requirement: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return a list of clarifying questions.

        Each question is a dict with at least ``question`` (str) and
        optionally ``options`` (list of suggested answers).
        """

    @abstractmethod
    async def plan(
        self,
        requirement: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return an implementation plan.

        The plan dict should contain at least ``steps`` (list of dicts
        each with ``description`` and ``files``).
        """

    @abstractmethod
    def code(
        self,
        requirement: dict[str, Any],
        plan: dict[str, Any],
        context: dict[str, Any] | None = None,
        work_dir: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream coding messages as an async iterator.

        Each yielded dict represents a message from the AI with at least
        a ``type`` key (e.g. ``text``, ``tool_use``, ``result``).
        """

    @abstractmethod
    def revise(
        self,
        feedback: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        work_dir: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream revision messages as an async iterator.

        *feedback* is a list of review comments / CI failures that the
        AI should address.
        """
