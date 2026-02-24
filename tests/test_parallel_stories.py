"""Tests for multi-story parallel support — project-level coding lock."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from opd.db.models import RoundStatus, RoundType, StoryStatus
from opd.engine.orchestrator import Orchestrator, TaskInfo


@pytest.fixture
def orch(orchestrator):
    """Alias for the shared orchestrator fixture."""
    return orchestrator


class TestHasCodingTask:
    """has_coding_task correctly identifies running ai_stage tasks per project."""

    def test_no_tasks(self, orch):
        assert orch.has_coding_task(1) is False

    def test_coding_task_detected(self, orch):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orch.register_task("10", task, project_id=1, task_type="ai_stage")
        assert orch.has_coding_task(1) is True
        task.cancel()

    def test_chat_task_not_detected(self, orch):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orch.register_task("chat_10", task, project_id=1, task_type="chat")
        assert orch.has_coding_task(1) is False
        task.cancel()

    def test_different_project_not_detected(self, orch):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orch.register_task("20", task, project_id=2, task_type="ai_stage")
        assert orch.has_coding_task(1) is False
        assert orch.has_coding_task(2) is True
        task.cancel()

    def test_done_task_not_detected(self, orch):
        """A completed task should not count as running."""
        fut = asyncio.get_event_loop().create_future()
        fut.set_result(None)  # Mark as done
        orch.register_task("30", fut, project_id=1, task_type="ai_stage")
        assert orch.has_coding_task(1) is False


class TestWorkspaceLock:
    """Workspace locks are lazily created and per-project."""

    def test_lazy_creation(self, orch):
        assert len(orch._workspace_locks) == 0
        lock = orch.get_workspace_lock(1)
        assert isinstance(lock, asyncio.Lock)
        assert len(orch._workspace_locks) == 1

    def test_reuse_same_project(self, orch):
        lock1 = orch.get_workspace_lock(5)
        lock2 = orch.get_workspace_lock(5)
        assert lock1 is lock2

    def test_different_projects_different_locks(self, orch):
        lock_a = orch.get_workspace_lock(1)
        lock_b = orch.get_workspace_lock(2)
        assert lock_a is not lock_b

    async def test_lock_serializes_access(self, orch):
        """Two coroutines sharing a lock should not overlap."""
        lock = orch.get_workspace_lock(1)
        order: list[str] = []

        async def worker(name: str):
            async with lock:
                order.append(f"{name}_start")
                await asyncio.sleep(0.01)
                order.append(f"{name}_end")

        await asyncio.gather(worker("a"), worker("b"))
        # One must fully complete before the other starts
        assert order[0].endswith("_start")
        assert order[1].endswith("_end")
        assert order[0][0] == order[1][0]  # Same worker


class TestCrossProjectIsolation:
    """Cross-project tasks don't interfere with each other."""

    def test_coding_tasks_isolated(self, orch):
        loop = asyncio.get_event_loop()
        t1 = loop.create_task(asyncio.sleep(100))
        t2 = loop.create_task(asyncio.sleep(100))
        orch.register_task("100", t1, project_id=1, task_type="ai_stage")
        orch.register_task("200", t2, project_id=2, task_type="ai_stage")
        # Each project has its own coding task
        assert orch.has_coding_task(1) is True
        assert orch.has_coding_task(2) is True
        # They don't block each other (different locks)
        lock1 = orch.get_workspace_lock(1)
        lock2 = orch.get_workspace_lock(2)
        assert lock1 is not lock2
        t1.cancel()
        t2.cancel()
