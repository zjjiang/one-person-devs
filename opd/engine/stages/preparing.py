"""Preparing stage: generate PRD from raw input."""

from __future__ import annotations

import logging

from opd.engine.context import build_preparing_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


class PreparingStage(Stage):
    """Generate a structured PRD from the story's raw input via AI."""

    required_capabilities = ["ai"]
    optional_capabilities = ["doc"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.raw_input:
            errors.append("Story raw_input is required for PRD generation")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        system_prompt, user_prompt = build_preparing_prompt(ctx.story, ctx.project)

        collected: list[str] = []
        async for msg in ai.provider.prepare_prd(system_prompt, user_prompt):
            if ctx.publish:
                await ctx.publish(msg)
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        prd_text = "\n".join(collected)
        if not prd_text.strip():
            return StageResult(success=False, errors=["AI returned empty PRD"])

        return StageResult(
            success=True,
            output={"prd": prd_text},
            next_status=None,  # waits for human confirm
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        errors: list[str] = []
        if "prd" not in result.output:
            errors.append("Stage output missing 'prd'")
        return errors
