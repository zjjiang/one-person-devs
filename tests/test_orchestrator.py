"""Tests for the orchestrator."""

import asyncio


from opd.engine.orchestrator import TaskInfo
from opd.engine.stages.base import Stage, StageResult



class DummyStage(Stage):
    required_capabilities = ["ai"]

    async def validate_preconditions(self, ctx):
        return []

    async def execute(self, ctx):
        return StageResult(success=True, output={"data": "ok"}, next_status="clarifying")


class FailingStage(Stage):
    required_capabilities = ["ai"]

    async def validate_preconditions(self, ctx):
        return ["precondition failed"]

    async def execute(self, ctx):
        return StageResult(success=False, errors=["should not reach"])


class TestOrchestrator:
    async def test_advance_success(self, orchestrator, mock_story, mock_project, mock_round):
        # Replace preparing stage with our dummy
        orchestrator._stages["preparing"] = DummyStage()
        result = await orchestrator.advance(mock_story, mock_project, mock_round)
        assert result.success
        assert mock_story.status == "clarifying"

    async def test_advance_precondition_failure(self, orchestrator, mock_story, mock_project,
                                                 mock_round):
        orchestrator._stages["preparing"] = FailingStage()
        result = await orchestrator.advance(mock_story, mock_project, mock_round)
        assert not result.success
        assert "precondition failed" in result.errors

    async def test_advance_no_stage_handler(self, orchestrator, mock_story, mock_project,
                                             mock_round):
        mock_story.status = "nonexistent"
        result = await orchestrator.advance(mock_story, mock_project, mock_round)
        assert not result.success

    def test_subscribe_unsubscribe(self, orchestrator):
        q = orchestrator.subscribe("round-1")
        assert isinstance(q, asyncio.Queue)
        orchestrator.unsubscribe("round-1", q)
        assert q not in orchestrator._subscribers.get("round-1", [])

    async def test_publish(self, orchestrator):
        q = orchestrator.subscribe("round-1")
        await orchestrator.publish("round-1", {"type": "test", "msg": "hello"})
        event = q.get_nowait()
        assert event["type"] == "test"

    def test_stop_nonexistent_task(self, orchestrator):
        assert orchestrator.stop_task("nonexistent") is False

    def test_register_task_with_metadata(self, orchestrator):
        """register_task stores TaskInfo with project_id and task_type."""
        dummy = asyncio.Future()
        orchestrator.register_task("s1", dummy, project_id=10, task_type="ai_stage")
        info = orchestrator._running_tasks["s1"]
        assert isinstance(info, TaskInfo)
        assert info.project_id == 10
        assert info.task_type == "ai_stage"
        assert info.task is dummy

    def test_unregister_task_removes_entry(self, orchestrator):
        dummy = asyncio.Future()
        orchestrator.register_task("s2", dummy, project_id=5, task_type="chat")
        orchestrator.unregister_task("s2")
        assert "s2" not in orchestrator._running_tasks

    def test_stop_task_with_taskinfo(self, orchestrator):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orchestrator.register_task("s3", task, project_id=1, task_type="ai_stage")
        assert orchestrator.stop_task("s3") is True
        assert task.cancelling() > 0

    def test_has_coding_task(self, orchestrator):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orchestrator.register_task("s4", task, project_id=7, task_type="ai_stage")
        assert orchestrator.has_coding_task(7) is True
        assert orchestrator.has_coding_task(99) is False
        task.cancel()

    def test_has_coding_task_ignores_chat(self, orchestrator):
        loop = asyncio.get_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        orchestrator.register_task("chat_1", task, project_id=7, task_type="chat")
        assert orchestrator.has_coding_task(7) is False
        task.cancel()

    def test_workspace_lock_lazy_creation(self, orchestrator):
        assert len(orchestrator._workspace_locks) == 0
        lock1 = orchestrator.get_workspace_lock(1)
        assert isinstance(lock1, asyncio.Lock)
        lock2 = orchestrator.get_workspace_lock(1)
        assert lock1 is lock2  # Same lock reused
        lock3 = orchestrator.get_workspace_lock(2)
        assert lock3 is not lock1  # Different project, different lock

    def test_running_task_count(self, orchestrator):
        loop = asyncio.get_event_loop()
        t1 = loop.create_task(asyncio.sleep(100))
        t2 = loop.create_task(asyncio.sleep(100))
        t3 = loop.create_task(asyncio.sleep(100))
        orchestrator.register_task("a", t1, project_id=1, task_type="ai_stage")
        orchestrator.register_task("b", t2, project_id=1, task_type="chat")
        orchestrator.register_task("c", t3, project_id=2, task_type="ai_stage")
        assert orchestrator.running_task_count(1) == 2
        assert orchestrator.running_task_count(2) == 1
        assert orchestrator.running_task_count(99) == 0
        t1.cancel()
        t2.cancel()
        t3.cancel()
