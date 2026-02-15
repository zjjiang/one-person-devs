"""Tests for the orchestrator."""

import asyncio


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
        await orchestrator._publish("round-1", {"type": "test", "msg": "hello"})
        event = q.get_nowait()
        assert event["type"] == "test"

    def test_stop_nonexistent_task(self, orchestrator):
        assert orchestrator.stop_task("nonexistent") is False
