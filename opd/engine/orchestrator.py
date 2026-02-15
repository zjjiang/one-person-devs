"""Orchestrator: coordinates stage execution, state transitions, and SSE streaming."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from opd.capabilities.registry import CapabilityRegistry
from opd.engine.stages.base import Stage, StageContext, StageResult
from opd.engine.state_machine import StateMachine

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central coordinator that drives Stories through their lifecycle."""

    def __init__(self, stages: dict[str, Stage], state_machine: StateMachine,
                 capabilities: CapabilityRegistry):
        self._stages = stages
        self._sm = state_machine
        self._caps = capabilities
        # Background task tracking
        self._running_tasks: dict[str, asyncio.Task] = {}
        # SSE pub/sub
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # --- SSE Pub/Sub ---

    def subscribe(self, round_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(round_id, []).append(queue)
        return queue

    def unsubscribe(self, round_id: str, queue: asyncio.Queue):
        subs = self._subscribers.get(round_id, [])
        if queue in subs:
            subs.remove(queue)

    async def _publish(self, round_id: str, event: dict):
        for queue in self._subscribers.get(round_id, []):
            queue.put_nowait(event)

    # --- Stage Execution ---

    async def advance(self, story, project, round_, action: str = "confirm",
                      payload: dict | None = None) -> StageResult:
        """Advance a story to the next stage.

        Steps:
        1. Build project-level registry (if overrides exist)
        2. Preflight capability check
        3. Validate preconditions
        4. Execute stage
        5. Validate output
        6. Transition state
        """
        current_status = story.status if isinstance(story.status, str) else story.status.value
        stage = self._stages.get(current_status)
        if not stage:
            return StageResult(success=False, errors=[f"No stage handler for status: {current_status}"])

        # 1. Build project-level registry if overrides exist
        registry = self._caps
        cap_configs = getattr(project, "capability_configs", None)
        if cap_configs:
            overrides = [
                {
                    "capability": c.capability,
                    "enabled": c.enabled,
                    "provider_override": c.provider_override,
                    "config_override": c.config_override,
                }
                for c in cap_configs
            ]
            if overrides:
                registry = await self._caps.with_project_overrides(overrides)

        # 2. Preflight
        preflight = await registry.preflight(
            stage.required_capabilities, stage.optional_capabilities
        )
        if not preflight.ok:
            return StageResult(success=False, errors=preflight.errors)

        # 3. Preconditions
        ctx = StageContext(story=story, project=project, round=round_, capabilities=registry)
        precondition_errors = await stage.validate_preconditions(ctx)
        if precondition_errors:
            return StageResult(success=False, errors=precondition_errors)

        # 4. Execute
        result = await stage.execute(ctx)

        # 5. Output validation
        if result.success:
            output_errors = await stage.validate_output(result)
            if output_errors:
                return StageResult(success=False, errors=output_errors)

        # 6. State transition
        if result.success and result.next_status:
            self._sm.transition(story, result.next_status)

        return result

    # --- Background AI Tasks ---

    async def run_ai_background(
        self,
        round_id: str,
        stage: Stage,
        ctx: StageContext,
        pre_start: Callable[[], Coroutine] | None = None,
        post_complete: Callable[[], Coroutine] | None = None,
    ):
        """Run an AI stage in the background with SSE streaming."""

        async def _task():
            try:
                if pre_start:
                    await pre_start()

                result = await stage.execute(ctx)

                if post_complete and result.success:
                    await post_complete()

                await self._publish(round_id, {"type": "done"})
                return result
            except Exception as e:
                logger.exception("Background AI task failed for round %s", round_id)
                await self._publish(round_id, {"type": "error", "message": str(e)})
                return StageResult(success=False, errors=[str(e)])
            finally:
                self._running_tasks.pop(round_id, None)

        task = asyncio.create_task(_task())
        self._running_tasks[round_id] = task

    def stop_task(self, round_id: str) -> bool:
        """Cancel a running background task."""
        task = self._running_tasks.get(round_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._caps
