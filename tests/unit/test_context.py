"""Unit tests for opd.engine.context prompt builders."""

from __future__ import annotations

import pytest

from opd.db.models import RuleCategory
from opd.engine.context import (
    build_system_prompt,
    build_plan_prompt,
    build_coding_prompt,
    build_revision_prompt,
)


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    """Tests for the system-level prompt builder."""

    def test_includes_project_name(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "# Project: Test Project" in result

    def test_includes_description(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "## Description" in result
        assert mock_project.description in result

    def test_includes_tech_stack(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "## Tech Stack" in result
        assert mock_project.tech_stack in result

    def test_includes_architecture(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "## Architecture" in result
        assert mock_project.architecture in result

    def test_includes_enabled_rules(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "## Project Rules" in result
        # rule-001 (coding, enabled) should appear
        assert "Use type hints on all public functions" in result
        # rule-002 (testing, enabled) should appear
        assert "Maintain 80% code coverage" in result

    def test_excludes_disabled_rules(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        # rule-003 is disabled
        assert "Do not use eval()" not in result

    def test_no_description_omits_section(self, mock_rules):
        from tests.conftest import _make_project
        project = _make_project(description=None)
        result = build_system_prompt(project, mock_rules)
        assert "## Description" not in result

    def test_no_tech_stack_omits_section(self, mock_rules):
        from tests.conftest import _make_project
        project = _make_project(tech_stack=None)
        result = build_system_prompt(project, mock_rules)
        assert "## Tech Stack" not in result

    def test_no_architecture_omits_section(self, mock_rules):
        from tests.conftest import _make_project
        project = _make_project(architecture=None)
        result = build_system_prompt(project, mock_rules)
        assert "## Architecture" not in result

    def test_empty_rules_omits_section(self, mock_project):
        result = build_system_prompt(mock_project, [])
        assert "## Project Rules" not in result

    def test_includes_closing_instruction(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "Follow the project rules strictly" in result

    def test_rules_show_category(self, mock_project, mock_rules):
        result = build_system_prompt(mock_project, mock_rules)
        assert "[coding]" in result
        assert "[testing]" in result


# ---------------------------------------------------------------------------
# build_plan_prompt
# ---------------------------------------------------------------------------

class TestBuildPlanPrompt:
    """Tests for the planning prompt builder."""

    def test_includes_story_title(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert "# Story: Implement login endpoint" in result

    def test_includes_requirement(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert mock_story.requirement in result

    def test_includes_acceptance_criteria(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert "## Acceptance Criteria" in result
        assert mock_story.acceptance_criteria in result

    def test_includes_round_info(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert "# Round #1" in result
        assert "initial" in result

    def test_includes_clarifications(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert "## Clarifications" in result
        assert "Should the endpoint support OAuth?" in result
        assert "Yes, support Google OAuth" in result

    def test_unanswered_clarification_shows_placeholder(
        self, mock_project, mock_story, mock_round_with_clarifications
    ):
        result = build_plan_prompt(
            mock_project, mock_story, mock_round_with_clarifications
        )
        assert "(not yet answered)" in result

    def test_includes_plan_instructions(
        self, mock_project, mock_story, mock_round
    ):
        result = build_plan_prompt(mock_project, mock_story, mock_round)
        assert "implementation plan" in result

    def test_no_clarifications_omits_section(
        self, mock_project, mock_story, mock_round
    ):
        # mock_round has empty clarifications list
        result = build_plan_prompt(mock_project, mock_story, mock_round)
        assert "## Clarifications" not in result


# ---------------------------------------------------------------------------
# build_coding_prompt
# ---------------------------------------------------------------------------

class TestBuildCodingPrompt:
    """Tests for the coding prompt builder."""

    def test_includes_story_block(
        self, mock_project, mock_story, mock_round, mock_clarifications
    ):
        result = build_coding_prompt(
            mock_project, mock_story, mock_round, mock_clarifications
        )
        assert "# Story: Implement login endpoint" in result
        assert mock_story.requirement in result

    def test_includes_round_block(
        self, mock_project, mock_story, mock_round, mock_clarifications
    ):
        result = build_coding_prompt(
            mock_project, mock_story, mock_round, mock_clarifications
        )
        assert "# Round #1" in result

    def test_includes_clarifications(
        self, mock_project, mock_story, mock_round, mock_clarifications
    ):
        result = build_coding_prompt(
            mock_project, mock_story, mock_round, mock_clarifications
        )
        assert "## Clarifications" in result
        assert "Should the endpoint support OAuth?" in result

    def test_includes_coding_instructions(
        self, mock_project, mock_story, mock_round, mock_clarifications
    ):
        result = build_coding_prompt(
            mock_project, mock_story, mock_round, mock_clarifications
        )
        assert "Implement the requirement" in result
        assert "Write tests for new functionality" in result

    def test_empty_clarifications(
        self, mock_project, mock_story, mock_round
    ):
        result = build_coding_prompt(
            mock_project, mock_story, mock_round, []
        )
        assert "## Clarifications" not in result


# ---------------------------------------------------------------------------
# build_revision_prompt
# ---------------------------------------------------------------------------

class TestBuildRevisionPrompt:
    """Tests for the revision prompt builder."""

    def test_includes_story_block(
        self, mock_project, mock_story, mock_round
    ):
        result = build_revision_prompt(
            mock_project, mock_story, mock_round, "Fix the error handling"
        )
        assert "# Story: Implement login endpoint" in result

    def test_includes_round_block(
        self, mock_project, mock_story, mock_round
    ):
        result = build_revision_prompt(
            mock_project, mock_story, mock_round, "Fix the error handling"
        )
        assert "# Round #1" in result

    def test_includes_feedback(
        self, mock_project, mock_story, mock_round
    ):
        feedback = "The error handling in login() is missing try/except"
        result = build_revision_prompt(
            mock_project, mock_story, mock_round, feedback
        )
        assert "## Review Feedback" in result
        assert feedback in result

    def test_includes_revision_instructions(
        self, mock_project, mock_story, mock_round
    ):
        result = build_revision_prompt(
            mock_project, mock_story, mock_round, "Fix bugs"
        )
        assert "Address the review feedback" in result
        assert "Do not introduce unrelated changes" in result

    def test_no_acceptance_criteria_omits_section(
        self, mock_project, mock_round
    ):
        from tests.conftest import _make_story
        story = _make_story(acceptance_criteria=None)
        result = build_revision_prompt(
            mock_project, story, mock_round, "Fix it"
        )
        assert "## Acceptance Criteria" not in result
