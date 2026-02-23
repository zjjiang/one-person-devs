"""Tests for stories_tasks.py helper functions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from opd.api.stories_tasks import _save_clarifications
from opd.engine.workspace import DOC_FIELD_MAP


class TestDocFieldMap:
    def test_all_fields_present(self):
        expected = {"prd", "technical_design", "detailed_design",
                    "coding_report", "test_guide"}
        assert set(DOC_FIELD_MAP.keys()) == expected

    def test_all_values_are_md(self):
        for filename in DOC_FIELD_MAP.values():
            assert filename.endswith(".md")


class TestSaveClarifications:
    def test_valid_json_array(self):
        db = MagicMock()
        story = SimpleNamespace(id=1)
        raw = 'Some text [{"question": "What DB?"}, {"question": "Auth method?"}] more text'
        _save_clarifications(db, story, raw)
        assert db.add.call_count == 2

    def test_empty_questions_skipped(self):
        db = MagicMock()
        story = SimpleNamespace(id=1)
        raw = '[{"question": ""}, {"question": "Valid?"}]'
        _save_clarifications(db, story, raw)
        assert db.add.call_count == 1

    def test_no_json_array(self):
        db = MagicMock()
        story = SimpleNamespace(id=1)
        raw = "No JSON here, just plain text"
        _save_clarifications(db, story, raw)
        db.add.assert_not_called()

    def test_invalid_json(self):
        db = MagicMock()
        story = SimpleNamespace(id=1)
        raw = "[invalid json content]"
        _save_clarifications(db, story, raw)
        db.add.assert_not_called()

    def test_missing_question_key(self):
        db = MagicMock()
        story = SimpleNamespace(id=1)
        raw = '[{"q": "no question key"}]'
        _save_clarifications(db, story, raw)
        db.add.assert_not_called()
