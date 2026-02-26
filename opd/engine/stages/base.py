"""Stage base class: defines the contract for each engineering stage."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opd.capabilities.registry import CapabilityRegistry
    from opd.db.models import Project, Round, Story

logger = logging.getLogger(__name__)

MAX_CONTINUATIONS = 3


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

    @staticmethod
    async def _collect_with_continuation(
        ctx: StageContext,
        ai_method: Callable[..., AsyncIterator[dict]],
        system_prompt: str,
        user_prompt: str,
        label: str,
        work_dir: str = "",
    ) -> str:
        """Collect AI output with automatic continuation for truncated responses.

        Args:
            ctx: Stage context (for publish callback).
            ai_method: Bound AI provider method (e.g., ai.provider.plan).
            system_prompt: System prompt for the AI call.
            user_prompt: Initial user prompt.
            label: Human-readable label for log messages (e.g., "Technical design").
            work_dir: Working directory for the AI provider.
        """
        from opd.engine.context import (
            build_continuation_prompt,
            is_output_complete,
            strip_completion_marker,
        )

        collected: list[str] = []
        async for msg in ai_method(system_prompt, user_prompt, work_dir):
            if ctx.publish:
                await ctx.publish(msg)
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        full_output = "\n".join(collected)

        for i in range(MAX_CONTINUATIONS):
            if is_output_complete(full_output) or not full_output.strip():
                break
            logger.info(
                "%s output truncated (round %d/%d, %d chars), continuing...",
                label, i + 1, MAX_CONTINUATIONS, len(full_output),
            )
            cont_prompt = build_continuation_prompt(full_output)
            cont_collected: list[str] = []
            async for msg in ai_method(system_prompt, cont_prompt, work_dir):
                if ctx.publish:
                    await ctx.publish(msg)
                if msg.get("type") == "assistant":
                    cont_collected.append(msg["content"])
            continuation = "\n".join(cont_collected)
            if not continuation.strip():
                break
            full_output = full_output + "\n" + continuation

        return strip_completion_marker(full_output)
