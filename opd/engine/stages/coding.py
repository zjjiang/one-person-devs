"""Coding stage: AI writes code based on detailed design."""

from __future__ import annotations

import logging

from opd.db.models import StoryStatus
from opd.engine.context import build_coding_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


class CodingStage(Stage):
    """Execute AI coding based on the detailed design. Runs as a background task."""

    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.detailed_design:
            errors.append("Story detailed_design is required for coding")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        system_prompt, user_prompt = build_coding_prompt(
            ctx.story, ctx.project, ctx.round,
        )

        # Resolve working directory from SCM provider config or round branch
        scm = ctx.capabilities.get("scm")
        work_dir = scm.provider.config.get("work_dir", "") if scm else ""

        collected: list[str] = []
        async for msg in ai.provider.code(system_prompt, user_prompt, work_dir):
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        return StageResult(
            success=True,
            output={"messages": collected},
            next_status=StoryStatus.verifying,
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        return []
