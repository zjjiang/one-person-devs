"""Tests for all engineering stages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


from opd.capabilities.base import Capability
from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import RoundStatus, RoundType, StoryStatus
from opd.engine.stages.base import StageContext, StageResult
from opd.engine.stages.clarifying import ClarifyingStage
from opd.engine.stages.coding import CodingStage, _build_coding_report, _build_test_guide
from opd.engine.stages.designing import DesigningStage
from opd.engine.stages.planning import PlanningStage
from opd.engine.stages.preparing import PreparingStage
from opd.engine.stages.verifying import VerifyingStage

from conftest import MockAIProvider


def _make_ctx(story=None, project=None, round_=None, registry=None, publish=None):
    """Build a StageContext with sensible defaults."""
    if project is None:
        project = SimpleNamespace(
            id=1, name="test", repo_url="https://github.com/t/r",
            description="", tech_stack="Python", architecture="",
            rules=[], workspace_dir="/tmp/test-ws",
        )
    if story is None:
        story = SimpleNamespace(
            id=1, title="Test", raw_input="Build login",
            status=StoryStatus.preparing, prd=None, confirmed_prd=None,
            technical_design=None, detailed_design=None,
            feature_tag=None, tasks=[], clarifications=[],
        )
    if round_ is None:
        round_ = SimpleNamespace(
            id=1, round_number=1, type=RoundType.initial,
            status=RoundStatus.active, branch_name="", pull_requests=[],
            close_reason=None,
        )
    if registry is None:
        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", MockAIProvider())
    return StageContext(
        story=story, project=project, round=round_,
        capabilities=registry, publish=publish,
    )


# ── PreparingStage ──


class TestPreparingStage:
    async def test_precondition_missing_raw_input(self):
        ctx = _make_ctx(story=SimpleNamespace(raw_input=""))
        errors = await PreparingStage().validate_preconditions(ctx)
        assert any("raw_input" in e for e in errors)

    async def test_precondition_ok(self):
        ctx = _make_ctx()
        errors = await PreparingStage().validate_preconditions(ctx)
        assert errors == []

    async def test_execute_success(self):
        ctx = _make_ctx()
        result = await PreparingStage().execute(ctx)
        assert result.success
        assert "prd" in result.output
        assert result.output["prd"]

    async def test_execute_no_ai(self):
        registry = CapabilityRegistry()  # empty
        ctx = _make_ctx(registry=registry)
        result = await PreparingStage().execute(ctx)
        assert not result.success
        assert "AI" in result.errors[0]

    async def test_execute_empty_response(self):
        class EmptyAI(MockAIProvider):
            async def prepare_prd(self, s, u):
                yield {"type": "assistant", "content": ""}
        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", EmptyAI())
        ctx = _make_ctx(registry=registry)
        result = await PreparingStage().execute(ctx)
        assert not result.success
        assert "empty" in result.errors[0].lower()

    async def test_execute_publishes_messages(self):
        published = []
        ctx = _make_ctx(publish=AsyncMock(side_effect=lambda m: published.append(m)))
        await PreparingStage().execute(ctx)
        assert len(published) > 0

    async def test_validate_output(self):
        stage = PreparingStage()
        ok = await stage.validate_output(StageResult(success=True, output={"prd": "x"}))
        assert ok == []
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert len(bad) == 1


# ── ClarifyingStage ──


class TestClarifyingStage:
    async def test_precondition_missing_prd(self):
        ctx = _make_ctx(story=SimpleNamespace(prd=None))
        errors = await ClarifyingStage().validate_preconditions(ctx)
        assert any("PRD" in e for e in errors)

    async def test_precondition_ok(self):
        ctx = _make_ctx(story=SimpleNamespace(prd="Some PRD"))
        errors = await ClarifyingStage().validate_preconditions(ctx)
        assert errors == []

    @patch("opd.engine.stages.clarifying.scan_workspace", return_value="")
    async def test_execute_success(self, _mock_scan):
        story = SimpleNamespace(
            prd="Some PRD", confirmed_prd=None, id=1, title="T",
            raw_input="x", feature_tag=None, tasks=[], clarifications=[],
            technical_design=None, detailed_design=None,
        )
        ctx = _make_ctx(story=story)
        result = await ClarifyingStage().execute(ctx)
        assert result.success
        assert "questions" in result.output

    async def test_validate_output(self):
        stage = ClarifyingStage()
        ok = await stage.validate_output(StageResult(success=True, output={"questions": "q"}))
        assert ok == []
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert len(bad) == 1


# ── PlanningStage ──


class TestPlanningStage:
    async def test_precondition_missing_prd(self):
        ctx = _make_ctx(story=SimpleNamespace(confirmed_prd=None, prd=None))
        errors = await PlanningStage().validate_preconditions(ctx)
        assert len(errors) == 1

    async def test_precondition_ok_with_prd(self):
        ctx = _make_ctx(story=SimpleNamespace(confirmed_prd=None, prd="PRD"))
        errors = await PlanningStage().validate_preconditions(ctx)
        assert errors == []

    async def test_execute_success(self):
        story = SimpleNamespace(
            confirmed_prd="PRD content", prd="PRD", id=1, title="T",
            raw_input="x", feature_tag=None, tasks=[], clarifications=[],
            technical_design=None, detailed_design=None,
        )
        ctx = _make_ctx(story=story)
        result = await PlanningStage().execute(ctx)
        assert result.success
        assert "technical_design" in result.output

    async def test_validate_output(self):
        stage = PlanningStage()
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert any("technical_design" in e for e in bad)


# ── DesigningStage ──


class TestDesigningStage:
    async def test_precondition_missing_td(self):
        ctx = _make_ctx(story=SimpleNamespace(technical_design=None, tasks=[]))
        errors = await DesigningStage().validate_preconditions(ctx)
        assert len(errors) == 2

    async def test_precondition_ok(self):
        ctx = _make_ctx(story=SimpleNamespace(
            technical_design="TD", tasks=[SimpleNamespace(id=1)],
        ))
        errors = await DesigningStage().validate_preconditions(ctx)
        assert errors == []

    async def test_execute_success(self):
        story = SimpleNamespace(
            confirmed_prd="PRD", prd="PRD", id=1, title="T",
            raw_input="x", feature_tag=None,
            tasks=[SimpleNamespace(id=1, title="t", description="d", depends_on="", order=1)],
            clarifications=[],
            technical_design="Tech design", detailed_design=None,
        )
        ctx = _make_ctx(story=story)
        result = await DesigningStage().execute(ctx)
        assert result.success
        assert "detailed_design" in result.output

    async def test_validate_output(self):
        stage = DesigningStage()
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert any("detailed_design" in e for e in bad)


# ── CodingStage ──


class TestCodingStage:
    async def test_precondition_missing_dd(self):
        ctx = _make_ctx(story=SimpleNamespace(detailed_design=None))
        errors = await CodingStage().validate_preconditions(ctx)
        assert any("detailed_design" in e for e in errors)

    async def test_precondition_ok(self):
        ctx = _make_ctx(story=SimpleNamespace(detailed_design="DD"))
        errors = await CodingStage().validate_preconditions(ctx)
        assert errors == []

    @patch("opd.engine.stages.coding.resolve_work_dir", return_value="/tmp")
    async def test_execute_success(self, _mock_dir):
        class CodingAI(MockAIProvider):
            async def code(self, system, user, work_dir):
                yield {"type": "assistant", "content": "Implemented login"}
                yield {"type": "tool", "content": "wrote file.py"}

        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", CodingAI())
        story = SimpleNamespace(
            id=1, title="Login", detailed_design="DD content",
            confirmed_prd="PRD", prd="PRD", raw_input="x",
            feature_tag=None, tasks=[], clarifications=[],
            technical_design="TD",
        )
        round_ = SimpleNamespace(
            id=1, round_number=1, type=RoundType.initial,
            status=RoundStatus.active, branch_name="opd/story-1-r1",
            pull_requests=[], close_reason=None,
        )
        ctx = _make_ctx(story=story, round_=round_, registry=registry)
        result = await CodingStage().execute(ctx)
        assert result.success
        assert "coding_report" in result.output
        assert "test_guide" in result.output
        assert result.next_status == StoryStatus.verifying

    async def test_validate_output(self):
        stage = CodingStage()
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert len(bad) == 2  # missing coding_report and test_guide


# ── VerifyingStage ──


class TestVerifyingStage:
    async def test_precondition_no_prs(self):
        ctx = _make_ctx(round_=SimpleNamespace(pull_requests=[]))
        errors = await VerifyingStage().validate_preconditions(ctx)
        assert any("pull requests" in e for e in errors)

    async def test_precondition_ok(self):
        ctx = _make_ctx(round_=SimpleNamespace(
            pull_requests=[SimpleNamespace(pr_url="http://pr")],
        ))
        errors = await VerifyingStage().validate_preconditions(ctx)
        assert errors == []

    async def test_execute_returns_success(self):
        ctx = _make_ctx()
        result = await VerifyingStage().execute(ctx)
        assert result.success
        assert result.output == {}
        assert result.next_status is None

    async def test_validate_output_always_ok(self):
        stage = VerifyingStage()
        assert await stage.validate_output(StageResult(success=True, output={})) == []


# ── Report builders ──


class TestBuildCodingReport:
    def test_basic_report(self):
        report = _build_coding_report(
            story_title="Login",
            round_number=1,
            branch_name="opd/story-1-r1",
            repo_url="https://github.com/t/r",
            pr_urls=[],
            assistant_msgs=["Implemented login page"],
            tool_msgs=["wrote login.py"],
        )
        assert "Login" in report
        assert "opd/story-1-r1" in report
        assert "Implemented login page" in report

    def test_no_branch(self):
        report = _build_coding_report("T", 1, None, None, [], [], [])
        assert "未创建" in report

    def test_tool_msgs_truncated(self):
        long_msg = "x" * 300
        report = _build_coding_report("T", 1, None, None, [], [], [long_msg])
        assert "..." in report


class TestBuildTestGuide:
    def test_with_branch(self):
        guide = _build_test_guide("Login", "opd/story-1-r1", None, ["Changes made"])
        assert "git checkout" in guide
        assert "opd/story-1-r1" in guide

    def test_without_branch(self):
        guide = _build_test_guide("Login", None, None, [])
        assert "未创建" in guide
