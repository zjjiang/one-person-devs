"""Clarifying stage: generate clarification questions from PRD."""

from __future__ import annotations

import logging

from opd.engine.context import build_clarifying_prompt
from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


class ClarifyingStage(Stage):
    """Analyze the PRD and produce clarification questions via AI."""

    required_capabilities = ["ai"]
    optional_capabilities = ["scm"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.story.prd:
            errors.append("Story PRD is required for clarification")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        ai = ctx.capabilities.get("ai")
        if not ai:
            return StageResult(success=False, errors=["AI capability not available"])

        system_prompt, user_prompt = build_clarifying_prompt(ctx.story, ctx.project)

        collected: list[str] = []
        async for msg in ai.provider.clarify(system_prompt, user_prompt):
            if msg.get("type") == "assistant":
                collected.append(msg["content"])

        questions_text = "\n".join(collected)
        if not questions_text.strip():
            return StageResult(success=False, errors=["AI returned no clarification questions"])

        return StageResult(
            success=True,
            output={"questions": questions_text},
            next_status=None,  # waits for human answers
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        errors: list[str] = []
        if "questions" not in result.output:
            errors.append("Stage output missing 'questions'")
        return errors
