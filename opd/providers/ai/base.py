"""AI Provider base class."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator

from opd.capabilities.base import Provider


class AIProvider(Provider):
    """Abstract base for AI coding capabilities."""

    @abstractmethod
    async def clarify(self, system_prompt: str, user_prompt: str) -> AsyncIterator[dict]:
        """Analyze requirements and generate clarification questions. Streams messages."""

    @abstractmethod
    async def plan(self, system_prompt: str, user_prompt: str) -> AsyncIterator[dict]:
        """Generate technical design and task breakdown. Streams messages."""

    @abstractmethod
    async def design(self, system_prompt: str, user_prompt: str) -> AsyncIterator[dict]:
        """Generate detailed design. Streams messages."""

    @abstractmethod
    async def code(self, system_prompt: str, user_prompt: str,
                   work_dir: str) -> AsyncIterator[dict]:
        """Execute coding task in work_dir. Streams messages."""

    @abstractmethod
    async def prepare_prd(self, system_prompt: str, user_prompt: str) -> AsyncIterator[dict]:
        """Generate/polish PRD from raw input. Streams messages."""

    @abstractmethod
    async def refine_prd(self, system_prompt: str, user_prompt: str) -> AsyncIterator[dict]:
        """Refine PRD based on user feedback in a conversational flow. Streams messages."""
