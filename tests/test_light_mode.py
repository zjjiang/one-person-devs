"""Tests for lightweight mode (briefing → coding → verifying → done)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from opd.capabilities.base import Capability
from opd.capabilities.registry import CapabilityRegistry
from opd.db.models import RoundStatus, RoundType, StoryMode, StoryStatus
from opd.engine.context import build_briefing_prompt, build_light_coding_prompt
from opd.engine.hashing import (
    LIGHT_STAGE_INPUT_MAP,
    _get_input_map,
    compute_hash,
    compute_stage_input_hash,
    get_stage_input_content,
    should_skip_ai,
)
from opd.engine.stages.base import StageContext, StageResult
from opd.engine.stages.briefing import BriefingStage
from opd.engine.stages.coding import CodingStage
from opd.engine.state_machine import (
    MODE_NEXT_STATUS,
    InvalidTransitionError,
    get_next_status,
)

from conftest import MockAIProvider


# ── Helpers ──


def _project(**kw):
    defaults = dict(
        id=1, name="test", repo_url="https://github.com/t/r",
        description="A test project", tech_stack="Python", architecture="monolith",
        rules=[], workspace_dir="/tmp/test-ws",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _story(**kw):
    defaults = dict(
        id=1, title="Fix bug", raw_input="Fix the login bug",
        status=StoryStatus.briefing, mode=StoryMode.light,
        prd=None, confirmed_prd=None, technical_design=None,
        detailed_design=None, coding_report=None, test_guide=None,
        feature_tag=None, tasks=[], clarifications=[],
        planning_input_hash=None, designing_input_hash=None,
        coding_input_hash=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _round(**kw):
    defaults = dict(
        id=1, round_number=1, type=RoundType.initial,
        status=RoundStatus.active, branch_name="",
        pull_requests=[], close_reason=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _make_ctx(story=None, project=None, round_=None, registry=None, publish=None):
    if project is None:
        project = _project()
    if story is None:
        story = _story()
    if round_ is None:
        round_ = _round()
    if registry is None:
        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", MockAIProvider())
    return StageContext(
        story=story, project=project, round=round_,
        capabilities=registry, publish=publish,
    )


# ── State Machine: Light Mode ──


class TestStateMachineLightMode:
    def test_briefing_to_coding(self, state_machine):
        story = _story()
        state_machine.transition(story, StoryStatus.coding)
        assert story.status == StoryStatus.coding

    def test_coding_to_verifying(self, state_machine):
        story = _story(status=StoryStatus.coding)
        state_machine.transition(story, StoryStatus.verifying)
        assert story.status == StoryStatus.verifying

    def test_verifying_to_done(self, state_machine):
        story = _story(status=StoryStatus.verifying)
        state_machine.transition(story, StoryStatus.done)
        assert story.status == StoryStatus.done

    def test_verifying_to_coding_iterate(self, state_machine):
        story = _story(status=StoryStatus.verifying)
        action = state_machine.transition(story, StoryStatus.coding)
        assert story.status == StoryStatus.coding
        assert action == "iterate"

    def test_verifying_to_briefing_restart(self, state_machine):
        story = _story(status=StoryStatus.verifying)
        action = state_machine.transition(story, StoryStatus.briefing)
        assert story.status == StoryStatus.briefing
        assert action == "restart"

    def test_coding_to_briefing_allowed(self, state_machine):
        story = _story(status=StoryStatus.coding)
        state_machine.transition(story, StoryStatus.briefing)
        assert story.status == StoryStatus.briefing

    def test_briefing_cannot_skip_to_verifying(self, state_machine):
        story = _story()
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(story, StoryStatus.verifying)

    def test_briefing_in_valid_transitions(self):
        from opd.engine.state_machine import VALID_TRANSITIONS
        assert StoryStatus.briefing in VALID_TRANSITIONS
        assert StoryStatus.coding in VALID_TRANSITIONS[StoryStatus.briefing]


class TestModeNextStatus:
    def test_light_mode_briefing_next(self):
        assert get_next_status("briefing", "light") == "coding"

    def test_light_mode_verifying_next(self):
        assert get_next_status("verifying", "light") == "done"

    def test_light_mode_coding_no_next(self):
        """Coding doesn't have a confirm next — it auto-transitions to verifying."""
        assert get_next_status("coding", "light") is None

    def test_full_mode_preparing_next(self):
        assert get_next_status("preparing", "full") == "clarifying"

    def test_light_mode_has_two_entries(self):
        assert len(MODE_NEXT_STATUS["light"]) == 2

    def test_unknown_mode_falls_back_to_full(self):
        assert get_next_status("preparing", "unknown") == "clarifying"


# ── BriefingStage ──


class TestBriefingStage:
    async def test_precondition_missing_raw_input(self):
        ctx = _make_ctx(story=_story(raw_input=""))
        errors = await BriefingStage().validate_preconditions(ctx)
        assert any("raw_input" in e for e in errors)

    async def test_precondition_ok(self):
        ctx = _make_ctx()
        errors = await BriefingStage().validate_preconditions(ctx)
        assert errors == []

    @patch("opd.engine.stages.briefing.resolve_work_dir", return_value="/tmp/test-ws")
    async def test_execute_success(self, _mock_dir):
        ctx = _make_ctx()
        result = await BriefingStage().execute(ctx)
        assert result.success
        assert "prd" in result.output
        assert result.output["prd"]
        assert result.next_status is None  # waits for confirm

    async def test_execute_no_ai(self):
        registry = CapabilityRegistry()
        ctx = _make_ctx(registry=registry)
        result = await BriefingStage().execute(ctx)
        assert not result.success
        assert "AI" in result.errors[0]

    async def test_execute_empty_response(self):
        class EmptyAI(MockAIProvider):
            async def prepare_prd(self, s, u, work_dir=""):
                yield {"type": "assistant", "content": ""}
        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", EmptyAI())
        ctx = _make_ctx(registry=registry)
        result = await BriefingStage().execute(ctx)
        assert not result.success
        assert "empty" in result.errors[0].lower()

    @patch("opd.engine.stages.briefing.resolve_work_dir", return_value="/tmp/test-ws")
    async def test_execute_publishes_messages(self, _mock_dir):
        published = []
        ctx = _make_ctx(publish=AsyncMock(side_effect=lambda m: published.append(m)))
        await BriefingStage().execute(ctx)
        assert len(published) > 0

    async def test_validate_output(self):
        stage = BriefingStage()
        ok = await stage.validate_output(StageResult(success=True, output={"prd": "x"}))
        assert ok == []
        bad = await stage.validate_output(StageResult(success=True, output={}))
        assert len(bad) == 1


# ── CodingStage: Light Mode ──


class TestCodingStageLightMode:
    async def test_precondition_light_needs_prd(self):
        story = _story(prd=None)
        ctx = _make_ctx(story=story)
        errors = await CodingStage().validate_preconditions(ctx)
        assert any("prd" in e for e in errors)

    async def test_precondition_light_ok_with_prd(self):
        story = _story(prd="Coding brief content")
        ctx = _make_ctx(story=story)
        errors = await CodingStage().validate_preconditions(ctx)
        assert errors == []

    async def test_precondition_full_needs_detailed_design(self):
        """Full mode still requires detailed_design, not prd."""
        story = _story(mode=StoryMode.full, detailed_design=None)
        ctx = _make_ctx(story=story)
        errors = await CodingStage().validate_preconditions(ctx)
        assert any("detailed_design" in e for e in errors)

    @patch("opd.engine.stages.coding.resolve_work_dir", return_value="/tmp")
    async def test_execute_light_mode(self, _mock_dir):
        class CodingAI(MockAIProvider):
            async def code(self, system, user, work_dir):
                yield {"type": "assistant", "content": "Fixed the bug"}
                yield {"type": "tool", "content": "wrote fix.py"}

        registry = CapabilityRegistry()
        registry._capabilities["ai"] = Capability("ai", CodingAI())
        story = _story(prd="Fix the login bug brief", status=StoryStatus.coding)
        round_ = _round(branch_name="opd/story-1-r1")
        ctx = _make_ctx(story=story, round_=round_, registry=registry)
        result = await CodingStage().execute(ctx)
        assert result.success
        assert "coding_report" in result.output
        assert "test_guide" in result.output
        assert result.next_status == StoryStatus.verifying


# ── Context: Briefing & Light Coding Prompts ──


class TestBuildBriefingPrompt:
    def test_returns_tuple(self):
        system, user = build_briefing_prompt(_story(), _project())
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_includes_raw_input(self):
        system, user = build_briefing_prompt(_story(), _project())
        assert "Fix the login bug" in user

    def test_system_includes_project_context(self):
        system, user = build_briefing_prompt(_story(), _project())
        assert "test" in system or "Python" in system

    def test_system_includes_structure_instructions(self):
        system, _ = build_briefing_prompt(_story(), _project())
        assert "改动目标" in system
        assert "验收标准" in system


class TestBuildLightCodingPrompt:
    def test_returns_tuple(self):
        story = _story(prd="Brief content")
        system, user = build_light_coding_prompt(story, _project(), _round())
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_includes_prd_content(self):
        story = _story(prd="Brief content here")
        _, user = build_light_coding_prompt(story, _project(), _round())
        assert "Brief content here" in user or "编码指引" in user

    def test_iterate_includes_feedback(self):
        story = _story(prd="Brief")
        round_ = _round(type=RoundType.iterate, close_reason="Fix the typo")
        _, user = build_light_coding_prompt(story, _project(), round_)
        assert "Fix the typo" in user


# ── Hashing: Light Mode ──


class TestHashingLightMode:
    def test_light_stage_input_map_coding(self):
        field, filename, hash_field, output_field = LIGHT_STAGE_INPUT_MAP["coding"]
        assert field == "prd"
        assert filename == "prd.md"
        assert hash_field == "coding_input_hash"
        assert output_field == "coding_report"

    def test_get_input_map_light(self):
        m = _get_input_map("light")
        assert "coding" in m
        assert "planning" not in m
        assert "designing" not in m

    def test_get_input_map_full(self):
        m = _get_input_map("full")
        assert "coding" in m
        assert "planning" in m
        assert "designing" in m

    def test_get_stage_input_content_light_coding(self):
        story = _story(prd="Brief content")
        project = _project()
        with patch("opd.engine.hashing.read_doc", return_value=None):
            content = get_stage_input_content(story, project, "coding", mode="light")
        assert content == "Brief content"

    def test_get_stage_input_content_light_unknown_stage(self):
        story = _story()
        project = _project()
        assert get_stage_input_content(story, project, "planning", mode="light") is None

    def test_compute_stage_input_hash_light(self):
        story = _story(prd="Brief content")
        project = _project()
        with patch("opd.engine.hashing.read_doc", return_value=None):
            h = compute_stage_input_hash(story, project, "coding", mode="light")
        assert h == compute_hash("Brief content")

    def test_should_skip_ai_light_coding(self):
        prd_hash = compute_hash("Brief content")
        story = _story(
            prd="Brief content",
            coding_report="some report",
            coding_input_hash=prd_hash,
        )
        project = _project()
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "coding", mode="light") is True

    def test_should_not_skip_ai_light_coding_changed(self):
        story = _story(
            prd="New brief content",
            coding_report="some report",
            coding_input_hash=compute_hash("Old brief content"),
        )
        project = _project()
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "coding", mode="light") is False

    def test_should_not_skip_ai_light_no_output(self):
        story = _story(
            prd="Brief content",
            coding_report=None,
            coding_input_hash=compute_hash("Brief content"),
        )
        project = _project()
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "coding", mode="light") is False
