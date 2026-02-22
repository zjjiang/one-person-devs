"""Tests for input hash change detection."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opd.engine.hashing import (
    STAGE_INPUT_MAP,
    compute_hash,
    compute_stage_input_hash,
    get_stage_input_content,
    should_skip_ai,
)


class TestComputeHash:
    def test_deterministic(self):
        assert compute_hash("hello") == compute_hash("hello")

    def test_different_content_different_hash(self):
        assert compute_hash("hello") != compute_hash("world")

    def test_sha256_format(self):
        h = compute_hash("test")
        assert len(h) == 64  # SHA-256 hex digest
        assert h == hashlib.sha256(b"test").hexdigest()

    def test_empty_string(self):
        h = compute_hash("")
        assert len(h) == 64


class TestStageInputMap:
    def test_planning_mapping(self):
        field, filename, hash_field, output_field = STAGE_INPUT_MAP["planning"]
        assert field == "confirmed_prd"
        assert filename == "prd.md"
        assert hash_field == "planning_input_hash"
        assert output_field == "technical_design"

    def test_designing_mapping(self):
        field, filename, hash_field, output_field = STAGE_INPUT_MAP["designing"]
        assert field == "technical_design"
        assert filename == "technical_design.md"
        assert hash_field == "designing_input_hash"
        assert output_field == "detailed_design"

    def test_coding_mapping(self):
        field, filename, hash_field, output_field = STAGE_INPUT_MAP["coding"]
        assert field == "detailed_design"
        assert filename == "detailed_design.md"
        assert hash_field == "coding_input_hash"
        assert output_field == "coding_report"

    def test_unknown_stage_not_in_map(self):
        assert "verifying" not in STAGE_INPUT_MAP
        assert "preparing" not in STAGE_INPUT_MAP


class TestGetStageInputContent:
    def test_reads_from_doc_file(self):
        story = SimpleNamespace(confirmed_prd="docs/1/prd.md")
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value="file content"):
            content = get_stage_input_content(story, project, "planning")
        assert content == "file content"

    def test_falls_back_to_db_field(self):
        story = SimpleNamespace(confirmed_prd="inline PRD content")
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            content = get_stage_input_content(story, project, "planning")
        assert content == "inline PRD content"

    def test_returns_none_for_unknown_stage(self):
        story = SimpleNamespace()
        project = SimpleNamespace()
        assert get_stage_input_content(story, project, "verifying") is None

    def test_returns_none_when_no_content(self):
        story = SimpleNamespace(confirmed_prd=None)
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert get_stage_input_content(story, project, "planning") is None

    def test_skips_db_field_if_path(self):
        """DB field starting with 'docs/' is a path, not inline content."""
        story = SimpleNamespace(confirmed_prd="docs/1/prd.md")
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert get_stage_input_content(story, project, "planning") is None


class TestComputeStageInputHash:
    def test_returns_hash_when_content_exists(self):
        story = SimpleNamespace(confirmed_prd="PRD content")
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            h = compute_stage_input_hash(story, project, "planning")
        assert h == compute_hash("PRD content")

    def test_returns_none_when_no_content(self):
        story = SimpleNamespace(confirmed_prd=None)
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert compute_stage_input_hash(story, project, "planning") is None

    def test_returns_none_for_unknown_stage(self):
        story = SimpleNamespace()
        project = SimpleNamespace()
        assert compute_stage_input_hash(story, project, "unknown") is None


class TestShouldSkipAI:
    def _make_story(self, **kwargs):
        defaults = {
            "confirmed_prd": "PRD content",
            "technical_design": None,
            "detailed_design": None,
            "coding_report": None,
            "planning_input_hash": None,
            "designing_input_hash": None,
            "coding_input_hash": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_skip_when_output_exists_and_hash_matches(self):
        prd_hash = compute_hash("PRD content")
        story = self._make_story(
            technical_design="some design",
            planning_input_hash=prd_hash,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "planning") is True

    def test_no_skip_when_hash_differs(self):
        story = self._make_story(
            technical_design="some design",
            planning_input_hash="old_hash_that_doesnt_match",
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "planning") is False

    def test_no_skip_when_no_output(self):
        prd_hash = compute_hash("PRD content")
        story = self._make_story(
            technical_design=None,
            planning_input_hash=prd_hash,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "planning") is False

    def test_no_skip_when_no_stored_hash(self):
        story = self._make_story(
            technical_design="some design",
            planning_input_hash=None,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "planning") is False

    def test_no_skip_for_unknown_stage(self):
        story = self._make_story()
        project = SimpleNamespace(name="test")
        assert should_skip_ai(story, project, "verifying") is False

    def test_designing_stage_skip(self):
        td_hash = compute_hash("tech design content")
        story = self._make_story(
            technical_design="tech design content",
            detailed_design="some detailed design",
            designing_input_hash=td_hash,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "designing") is True

    def test_coding_stage_skip(self):
        dd_hash = compute_hash("detailed design content")
        story = self._make_story(
            detailed_design="detailed design content",
            coding_report="some report",
            coding_input_hash=dd_hash,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "coding") is True

    def test_input_change_detected_after_edit(self):
        """Simulate: user edits PRD after planning was generated."""
        old_hash = compute_hash("old PRD")
        story = self._make_story(
            confirmed_prd="new PRD content",  # edited
            technical_design="some design",
            planning_input_hash=old_hash,
        )
        project = SimpleNamespace(name="test")
        with patch("opd.engine.hashing.read_doc", return_value=None):
            assert should_skip_ai(story, project, "planning") is False
