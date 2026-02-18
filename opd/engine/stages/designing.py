"""Designing stage: generate detailed design from technical design and tasks."""

from __future__ import annotations

import logging

from opd.engine.context import (
    build_continuation_prompt,
    build_designing_prompt,
    is_output_complete,
    strip_completion_marker,
)
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

MAX_CONTINUATIONS = 3


class DesigningStage(Stage):
    """Produce a detailed design document covering all tasks via AI."""

    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.technical_design:
            errors.append("Story technical_design is required for detailed design")
        if not ctx.story.tasks:
            errors.append("Story must have tasks before detailed design")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        system_prompt, user_prompt = build_designing_prompt(ctx.story, ctx.project)

        collected: list[str] = []
        async for msg in ai.provider.design(system_prompt, user_prompt):
            if ctx.publish:
                await ctx.publish(msg)
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        full_output = "\n".join(collected)

        # Continuation loop: if output is truncated, ask AI to continue
        for i in range(MAX_CONTINUATIONS):
            if is_output_complete(full_output) or not full_output.strip():
                break
            logger.info(
                "Detailed design output truncated (round %d/%d, %d chars), continuing...",
                i + 1, MAX_CONTINUATIONS, len(full_output),
            )
            cont_prompt = build_continuation_prompt(full_output)
            cont_collected: list[str] = []
            async for msg in ai.provider.design(system_prompt, cont_prompt):
                if ctx.publish:
                    await ctx.publish(msg)
                if msg.get("type") == "assistant":
                    cont_collected.append(msg["content"])
            continuation = "\n".join(cont_collected)
            if not continuation.strip():
                break
            full_output = full_output + "\n" + continuation

        detailed_design = strip_completion_marker(full_output)
        if not detailed_design.strip():
            return StageResult(success=False, errors=["AI returned empty detailed design"])

        return StageResult(
            success=True,
            output={"detailed_design": detailed_design},
            next_status=None,
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        errors: list[str] = []
        if "detailed_design" not in result.output:
            errors.append("Stage output missing 'detailed_design'")
        return errors
