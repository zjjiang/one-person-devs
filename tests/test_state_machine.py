"""Tests for the Story state machine."""

import pytest

from opd.db.models import StoryStatus
from opd.engine.state_machine import InvalidTransitionError, VALID_TRANSITIONS


class TestStateMachine:
    def test_valid_transitions_completeness(self):
        """All non-terminal statuses should have transitions defined."""
        for status in StoryStatus:
            if status != StoryStatus.done:
                assert status in VALID_TRANSITIONS

    def test_forward_transitions(self, state_machine, mock_story):
        """Happy path: preparing → clarifying → ... → done."""
        path = ["clarifying", "planning", "designing", "coding", "verifying", "done"]
        for next_status in path:
            current = mock_story.status
            current_val = current.value if hasattr(current, "value") else current
            assert state_machine.can_transition(current_val, next_status)
            state_machine.transition(mock_story, next_status)
            assert mock_story.status == next_status

    def test_invalid_transition_raises(self, state_machine, mock_story):
        """Cannot skip stages."""
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(mock_story, "coding")

    def test_iterate_from_verifying(self, state_machine, mock_story):
        """Verifying → coding (iterate)."""
        mock_story.status = StoryStatus.verifying
        action = state_machine.transition(mock_story, StoryStatus.coding)
        assert mock_story.status == StoryStatus.coding
        assert action == "iterate"

    def test_restart_from_verifying(self, state_machine, mock_story):
        """Verifying → designing (restart)."""
        mock_story.status = StoryStatus.verifying
        action = state_machine.transition(mock_story, StoryStatus.designing)
        assert mock_story.status == StoryStatus.designing
        assert action == "restart"

    def test_available_transitions(self, state_machine):
        assert StoryStatus.clarifying in state_machine.available_transitions(StoryStatus.preparing)
        assert StoryStatus.done in state_machine.available_transitions(StoryStatus.verifying)
        assert state_machine.available_transitions(StoryStatus.done) == []

    def test_cannot_go_backwards(self, state_machine, mock_story):
        mock_story.status = StoryStatus.coding
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(mock_story, StoryStatus.planning)
