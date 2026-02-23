"""Designing stage: generate detailed design from technical design and tasks."""

from __future__ import annotations

from opd.engine.context import build_designing_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult


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

        detailed_design = await self._collect_with_continuation(
            ctx, ai.provider.design, system_prompt, user_prompt, "Detailed design",
        )
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
