"""Unit tests for opd.engine.state_machine."""

from __future__ import annotations

import pytest

from opd.db.models import RoundStatus
from opd.engine.state_machine import (
    InvalidTransitionError,
    StateMachine,
    VALID_TRANSITIONS,
)


@pytest.fixture
def sm():
    """Return a fresh StateMachine instance."""
    return StateMachine()


# ---------------------------------------------------------------------------
# Tests for valid transitions
# ---------------------------------------------------------------------------

class TestValidTransitions:
    """Verify every edge in the VALID_TRANSITIONS table."""

    @pytest.mark.parametrize(
        "current, target",
        [
            (RoundStatus.created, RoundStatus.clarifying),
            (RoundStatus.created, RoundStatus.planning),
            (RoundStatus.clarifying, RoundStatus.planning),
            (RoundStatus.planning, RoundStatus.coding),
            (RoundStatus.coding, RoundStatus.pr_created),
            (RoundStatus.pr_created, RoundStatus.reviewing),
            (RoundStatus.reviewing, RoundStatus.revising),
            (RoundStatus.reviewing, RoundStatus.testing),
            (RoundStatus.reviewing, RoundStatus.done),
            (RoundStatus.revising, RoundStatus.reviewing),
            (RoundStatus.testing, RoundStatus.done),
            (RoundStatus.testing, RoundStatus.reviewing),
        ],
    )
    def test_transition_succeeds(self, sm, current, target):
        result = sm.transition(current, target)
        assert result is target


# ---------------------------------------------------------------------------
# Tests for invalid transitions
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    """Verify that disallowed transitions raise InvalidTransitionError."""

    @pytest.mark.parametrize(
        "current, target",
        [
            # Cannot skip ahead
            (RoundStatus.created, RoundStatus.coding),
            (RoundStatus.created, RoundStatus.done),
            (RoundStatus.clarifying, RoundStatus.coding),
            (RoundStatus.planning, RoundStatus.pr_created),
            # Cannot go backwards (except revising -> reviewing)
            (RoundStatus.coding, RoundStatus.planning),
            (RoundStatus.pr_created, RoundStatus.coding),
            (RoundStatus.reviewing, RoundStatus.coding),
            # Terminal state: done -> anything
            (RoundStatus.done, RoundStatus.created),
            (RoundStatus.done, RoundStatus.clarifying),
            (RoundStatus.done, RoundStatus.planning),
            (RoundStatus.done, RoundStatus.coding),
            (RoundStatus.done, RoundStatus.reviewing),
            # Self-transitions are not allowed
            (RoundStatus.created, RoundStatus.created),
            (RoundStatus.planning, RoundStatus.planning),
            (RoundStatus.done, RoundStatus.done),
        ],
    )
    def test_transition_raises(self, sm, current, target):
        with pytest.raises(InvalidTransitionError) as exc_info:
            sm.transition(current, target)
        assert exc_info.value.current is current
        assert exc_info.value.target is target
        assert current.value in str(exc_info.value)
        assert target.value in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests for can_transition
# ---------------------------------------------------------------------------

class TestCanTransition:
    """Verify the boolean can_transition helper."""

    def test_returns_true_for_valid(self, sm):
        assert sm.can_transition(RoundStatus.created, RoundStatus.clarifying) is True

    def test_returns_false_for_invalid(self, sm):
        assert sm.can_transition(RoundStatus.done, RoundStatus.coding) is False

    def test_returns_false_for_self_transition(self, sm):
        assert sm.can_transition(RoundStatus.planning, RoundStatus.planning) is False

    def test_all_valid_transitions_return_true(self, sm):
        for current, targets in VALID_TRANSITIONS.items():
            for target in targets:
                assert sm.can_transition(current, target) is True, (
                    f"Expected can_transition({current}, {target}) to be True"
                )


# ---------------------------------------------------------------------------
# Tests for available_transitions
# ---------------------------------------------------------------------------

class TestAvailableTransitions:
    """Verify available_transitions returns the correct list."""

    def test_created_has_two_options(self, sm):
        result = sm.available_transitions(RoundStatus.created)
        assert set(result) == {RoundStatus.clarifying, RoundStatus.planning}

    def test_done_has_no_options(self, sm):
        result = sm.available_transitions(RoundStatus.done)
        assert result == []

    def test_reviewing_has_three_options(self, sm):
        result = sm.available_transitions(RoundStatus.reviewing)
        assert set(result) == {
            RoundStatus.revising,
            RoundStatus.testing,
            RoundStatus.done,
        }

    def test_returns_list_copy(self, sm):
        """Ensure the returned list is a copy, not the original."""
        result1 = sm.available_transitions(RoundStatus.created)
        result2 = sm.available_transitions(RoundStatus.created)
        assert result1 == result2
        assert result1 is not result2

    def test_all_statuses_have_entries(self, sm):
        """Every RoundStatus should be a key in VALID_TRANSITIONS."""
        for status in RoundStatus:
            result = sm.available_transitions(status)
            assert isinstance(result, list)
