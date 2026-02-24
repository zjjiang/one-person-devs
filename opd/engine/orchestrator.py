"""Orchestrator: coordinates stage execution, state transitions, and SSE streaming."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from opd.capabilities.registry import CapabilityRegistry, build_capability_overrides
from opd.engine.stages.base import Stage, StageContext, StageResult
from opd.engine.state_machine import StateMachine

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """Metadata for a registered background task."""

    task: asyncio.Task
    project_id: int | None = None
    task_type: str = ""  # "ai_stage", "chat", "sync", "clone", etc.


class Orchestrator:
    """Central coordinator that drives Stories through their lifecycle."""

    def __init__(self, stages: dict[str, Stage], state_machine: StateMachine,
                 capabilities: CapabilityRegistry):
        self._stages = stages
        self._sm = state_machine
        self._caps = capabilities
        # Background task tracking
        self._running_tasks: dict[str, TaskInfo] = {}
        # Per-project workspace locks (lazily created)
        self._workspace_locks: dict[int, asyncio.Lock] = {}
        # SSE pub/sub
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    # --- Public accessors ---

    def get_stage(self, status: str) -> Stage | None:
        """Return the stage handler for a given status."""
        return self._stages.get(status)

    def is_task_running(self, key: str) -> bool:
        """Check if a background task is registered under the given key."""
        info = self._running_tasks.get(key)
        return info is not None and not info.task.done()

    def register_task(self, key: str, task: asyncio.Task, *,
                      project_id: int | None = None, task_type: str = "") -> None:
        """Register a background task for tracking."""
        self._running_tasks[key] = TaskInfo(
            task=task, project_id=project_id, task_type=task_type,
        )

    def unregister_task(self, key: str) -> None:
        """Remove a background task from tracking."""
        self._running_tasks.pop(key, None)

    def get_workspace_lock(self, project_id: int) -> asyncio.Lock:
        """Return (lazily create) a per-project workspace lock."""
        lock = self._workspace_locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._workspace_locks[project_id] = lock
        return lock

    def has_coding_task(self, project_id: int) -> bool:
        """Check if any ai_stage task is running for the given project."""
        for info in self._running_tasks.values():
            if (info.project_id == project_id
                    and info.task_type == "ai_stage"
                    and not info.task.done()):
                return True
        return False

    def running_task_count(self, project_id: int) -> int:
        """Count running tasks for a given project."""
        return sum(
            1 for info in self._running_tasks.values()
            if info.project_id == project_id and not info.task.done()
        )

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

    def stop_task(self, key: str) -> bool:
        """Cancel a running background task."""
        info = self._running_tasks.get(key)
        if info and not info.task.done():
            info.task.cancel()
            return True
        return False

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._caps
