"""Verifying stage: human-driven verification of the coding output."""

from __future__ import annotations

import logging

from opd.engine.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


class VerifyingStage(Stage):
    """Human-driven verification. The actual work happens through API actions
    (confirm / iterate / restart). This stage simply signals readiness."""

    required_capabilities = ["scm"]
    optional_capabilities = ["ci", "sandbox"]

    async def validate_preconditions(self, ctx: StageContext) -> list[str]:
        errors: list[str] = []
        if not ctx.round.pull_requests:
            errors.append("Round must have pull requests before verification")
        return errors

    async def execute(self, ctx: StageContext) -> StageResult:
        return StageResult(
            success=True,
            output={},
            next_status=None,  # human decides next transition
        )

    async def validate_output(self, result: StageResult) -> list[str]:
        return []
