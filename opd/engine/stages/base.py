"""Stage base class: defines the contract for each engineering stage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opd.capabilities.registry import CapabilityRegistry
    from opd.db.models import Project, Round, Story


@dataclass
class StageContext:
    """Data passed between stages via the orchestrator."""

    story: Story
    project: Project
    round: Round
    capabilities: CapabilityRegistry
    publish: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None


@dataclass
class StageResult:
    """Result of a stage execution."""

    success: bool
    output: dict = field(default_factory=dict)
    next_status: str | None = None
    errors: list[str] = field(default_factory=list)


class Stage(ABC):
    """Base class for all engineering stages.

    Each stage declares its capability requirements and implements
    three contract methods: validate_preconditions, execute, validate_output.
    """

    # Subclasses declare which capabilities they need
    required_capabilities: list[str] = []
    optional_capabilities: list[str] = []

    @abstractmethod
    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """Check that all preconditions are met before execution.

        Returns a list of error messages (empty = all good).
        """

    @abstractmethod
    async def execute(self, ctx: StageContext) -> StageResult:
        """Execute the stage logic."""

    async def validate_output(self, result: StageResult) -> list[str]:
        """Validate the stage output. Override if needed.

        Returns a list of error messages (empty = all good).
        """
        return []
