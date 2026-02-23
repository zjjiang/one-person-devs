"""Tests for AI prompt context builders."""

from __future__ import annotations

from types import SimpleNamespace

from opd.db.models import RoundType
from opd.engine.context import (
    COMPLETION_MARKER,
    build_clarifying_chat_prompt,
    build_clarifying_prompt,
    build_coding_prompt,
    build_continuation_prompt,
    build_designing_chat_prompt,
    build_designing_prompt,
    build_planning_chat_prompt,
    build_planning_prompt,
    build_preparing_prompt,
    build_project_context,
    build_refine_prd_prompt,
    is_output_complete,
    parse_refine_response,
    strip_completion_marker,
)


def _project(**kw):
    defaults = dict(
        id=1, name="test", repo_url="https://github.com/t/r",
        description="A test project", tech_stack="Python", architecture="monolith",
        rules=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _story(**kw):
    defaults = dict(
        id=1, title="Login", raw_input="Build login page",
        prd="PRD content", confirmed_prd="Confirmed PRD",
        technical_design="Tech design", detailed_design="Detailed design",
        feature_tag=None, tasks=[], clarifications=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _round(**kw):
    defaults = dict(
        id=1, round_number=1, type=RoundType.initial,
        close_reason=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestBuildProjectContext:
    def test_includes_project_info(self):
        ctx = build_project_context(_project())
        assert "test" in ctx
        assert "Python" in ctx

    def test_includes_rules(self):
        cat = SimpleNamespace(value="general")
        rules = [SimpleNamespace(content="Rule 1", enabled=True, category=cat), SimpleNamespace(content="Rule 2", enabled=True, category=cat)]
        ctx = build_project_context(_project(rules=rules))
        assert "Rule 1" in ctx
        assert "Rule 2" in ctx


class TestBuildPreparingPrompt:
    def test_returns_tuple(self):
        system, user = build_preparing_prompt(_story(), _project())
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "Build login page" in user


class TestBuildClarifyingPrompt:
    def test_includes_prd(self):
        system, user = build_clarifying_prompt(_story(), _project())
        assert "PRD" in user or "prd" in user.lower()

    def test_includes_source_context(self):
        system, user = build_clarifying_prompt(
            _story(), _project(), source_context="## src/main.py",
        )
        assert "src/main.py" in user


class TestBuildPlanningPrompt:
    def test_returns_prompts(self):
        system, user = build_planning_prompt(_story(), _project())
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_includes_completion_marker_instruction(self):
        system, user = build_planning_prompt(_story(), _project())
        assert COMPLETION_MARKER in system or COMPLETION_MARKER in user


class TestBuildDesigningPrompt:
    def test_returns_prompts(self):
        story = _story(tasks=[
            SimpleNamespace(id=1, title="Task 1", description="Do thing", depends_on="", order=1),
        ])
        system, user = build_designing_prompt(story, _project())
        assert isinstance(system, str)
        assert "Task 1" in user or "Tech design" in user


class TestBuildCodingPrompt:
    def test_basic(self):
        system, user = build_coding_prompt(_story(), _project(), _round())
        assert "详细设计" in system or "详细设计" in user

    def test_iterate_round_includes_feedback(self):
        r = _round(type=RoundType.iterate, close_reason="Fix the bug")
        system, user = build_coding_prompt(_story(), _project(), r)
        assert "Fix the bug" in user

    def test_restart_round_includes_reason(self):
        r = _round(type=RoundType.restart, close_reason="Wrong approach")
        system, user = build_coding_prompt(_story(), _project(), r)
        assert "Wrong approach" in user


class TestContinuationPrompt:
    def test_includes_tail(self):
        prompt = build_continuation_prompt("Hello world output", tail_chars=10)
        assert "orld output" in prompt or "output" in prompt

    def test_includes_marker_instruction(self):
        prompt = build_continuation_prompt("some text")
        assert COMPLETION_MARKER in prompt


class TestCompletionMarker:
    def test_is_output_complete_true(self):
        assert is_output_complete(f"Some text\n{COMPLETION_MARKER}\n")

    def test_is_output_complete_false(self):
        assert not is_output_complete("Some text without marker")

    def test_strip_marker(self):
        text = f"Content here\n{COMPLETION_MARKER}\n"
        result = strip_completion_marker(text)
        assert COMPLETION_MARKER not in result
        assert "Content here" in result

    def test_strip_marker_no_marker(self):
        assert strip_completion_marker("plain text") == "plain text"


class TestParseRefineResponse:
    def test_with_both_tags(self):
        text = "<discussion>Looks good</discussion>\n<updated_doc>New doc</updated_doc>"
        disc, doc = parse_refine_response(text)
        assert disc == "Looks good"
        assert doc == "New doc"

    def test_discussion_only(self):
        text = "<discussion>No changes needed</discussion>"
        disc, doc = parse_refine_response(text)
        assert disc == "No changes needed"
        assert doc is None

    def test_legacy_updated_prd_tag(self):
        text = "<discussion>Updated</discussion>\n<updated_prd>New PRD</updated_prd>"
        disc, doc = parse_refine_response(text)
        assert disc == "Updated"
        assert doc == "New PRD"

    def test_no_tags_fallback(self):
        text = "Just a plain response"
        disc, doc = parse_refine_response(text)
        assert disc == "Just a plain response"
        assert doc is None

    def test_long_no_tags_truncated(self):
        text = "这是一段很长的回复。" * 100
        disc, doc = parse_refine_response(text)
        assert len(disc) < len(text)


# ── Chat prompt builders ──


class TestBuildRefinePrdPrompt:
    def test_includes_prd_and_message(self):
        system, user = build_refine_prd_prompt(
            _story(), _project(), [], "请修改验收标准",
        )
        assert "产品经理" in system
        assert "请修改验收标准" in user

    def test_includes_history(self):
        history = [{"role": "user", "content": "改一下"}, {"role": "assistant", "content": "好的"}]
        system, user = build_refine_prd_prompt(
            _story(), _project(), history, "继续",
        )
        assert "改一下" in user
        assert "好的" in user


class TestBuildClarifyingChatPrompt:
    def test_includes_prd_and_message(self):
        system, user = build_clarifying_chat_prompt(
            _story(), _project(), [], "这个需求边界是什么",
        )
        assert "研发工程师" in system
        assert "这个需求边界是什么" in user

    def test_includes_clarifications(self):
        story = _story(clarifications=[
            SimpleNamespace(question="Q1?", answer="A1"),
        ])
        _, user = build_clarifying_chat_prompt(story, _project(), [], "继续")
        assert "Q1?" in user


class TestBuildPlanningChatPrompt:
    def test_includes_td_and_message(self):
        system, user = build_planning_chat_prompt(
            _story(), _project(), [], "方案需要调整",
        )
        assert "架构师" in system
        assert "方案需要调整" in user


class TestBuildDesigningChatPrompt:
    def test_includes_dd_and_message(self):
        system, user = build_designing_chat_prompt(
            _story(), _project(), [], "详细设计需要补充",
        )
        assert "高级开发者" in system
        assert "详细设计需要补充" in user

    def test_includes_tasks(self):
        story = _story(tasks=[
            SimpleNamespace(id=1, title="T1", description="D1", depends_on="", order=1),
        ])
        _, user = build_designing_chat_prompt(story, _project(), [], "看看")
        assert "T1" in user
