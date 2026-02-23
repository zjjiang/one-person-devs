"""Orchestrator: coordinates stage execution, state transitions, and SSE streaming."""

from __future__ import annotations

import asyncio
import logging

from opd.capabilities.registry import CapabilityRegistry, build_capability_overrides
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

    # --- Public accessors ---

    def get_stage(self, status: str) -> Stage | None:
        """Return the stage handler for a given status."""
        return self._stages.get(status)

    def is_task_running(self, key: str) -> bool:
        """Check if a background task is registered under the given key."""
        return key in self._running_tasks

    def register_task(self, key: str, task: asyncio.Task) -> None:
        """Register a background task for tracking."""
        self._running_tasks[key] = task

    def unregister_task(self, key: str) -> None:
        """Remove a background task from tracking."""
        self._running_tasks.pop(key, None)

    # --- SSE Pub/Sub ---

    def subscribe(self, round_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(round_id, []).append(queue)
        return queue

    def unsubscribe(self, round_id: str, queue: asyncio.Queue):
        subs = self._subscribers.get(round_id, [])
        if queue in subs:
            subs.remove(queue)

    async def publish(self, round_id: str, event: dict):
        for queue in self._subscribers.get(round_id, []):
            queue.put_nowait(event)

    # --- Stage Execution ---

    async def advance(self, story, project, round_, action: str = "confirm",
                      payload: dict | None = None) -> StageResult:
        """Advance a story to the next stage."""
        current_status = story.status if isinstance(story.status, str) else story.status.value
        stage = self._stages.get(current_status)
        if not stage:
            return StageResult(success=False, errors=[f"No stage handler for status: {current_status}"])

        registry = self._caps
        cap_configs = getattr(project, "capability_configs", None)
        if cap_configs:
            overrides = build_capability_overrides(cap_configs)
            if overrides:
                registry = await self._caps.with_project_overrides(overrides)

        preflight = await registry.preflight(
            stage.required_capabilities, stage.optional_capabilities
        )
        if not preflight.ok:
            return StageResult(success=False, errors=preflight.errors)

        ctx = StageContext(story=story, project=project, round=round_, capabilities=registry)
        precondition_errors = await stage.validate_preconditions(ctx)
        if precondition_errors:
            return StageResult(success=False, errors=precondition_errors)

        result = await stage.execute(ctx)

        if result.success:
            output_errors = await stage.validate_output(result)
            if output_errors:
                return StageResult(success=False, errors=output_errors)

        if result.success and result.next_status:
            self._sm.transition(story, result.next_status)

        return result

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
