"""Planning stage: generate technical design and task breakdown."""

from __future__ import annotations

import logging

from opd.engine.context import build_planning_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


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
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        technical_design = "\n".join(collected)
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
