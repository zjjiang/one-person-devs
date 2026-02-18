"""Planning stage: generate technical design and task breakdown."""

from __future__ import annotations

import logging

from opd.engine.context import (
    build_continuation_prompt,
    build_planning_prompt,
    is_output_complete,
    strip_completion_marker,
)
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

MAX_CONTINUATIONS = 3


class PlanningStage(Stage):
    """Produce a technical design and task list from the confirmed PRD via AI."""

    required_capabilities = ["ai", "scm"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.confirmed_prd and not ctx.story.prd:
            errors.append("Story confirmed_prd or prd is required for planning")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        system_prompt, user_prompt = build_planning_prompt(ctx.story, ctx.project)

        collected: list[str] = []
        async for msg in ai.provider.plan(system_prompt, user_prompt):
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
                "Technical design output truncated (round %d/%d, %d chars), continuing...",
                i + 1, MAX_CONTINUATIONS, len(full_output),
            )
            cont_prompt = build_continuation_prompt(full_output)
            cont_collected: list[str] = []
            async for msg in ai.provider.plan(system_prompt, cont_prompt):
                if ctx.publish:
                    await ctx.publish(msg)
                if msg.get("type") == "assistant":
                    cont_collected.append(msg["content"])
            continuation = "\n".join(cont_collected)
            if not continuation.strip():
                break
            full_output = full_output + "\n" + continuation

        technical_design = strip_completion_marker(full_output)
        if not technical_design.strip():
            return StageResult(success=False, errors=["AI returned empty technical design"])

        return StageResult(
            success=True,
            output={"technical_design": technical_design},
            next_status=None,
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        errors: list[str] = []
        if "technical_design" not in result.output:
            errors.append("Stage output missing 'technical_design'")
        return errors
