"""State machine for Round status transitions.

Defines valid transitions between Round statuses and enforces them
at the engine layer before any database writes occur.
"""

from __future__ import annotations

from opd.db.models import RoundStatus


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: RoundStatus, target: RoundStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid transition from '{current.value}' to '{target.value}'"
        )


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[RoundStatus, list[RoundStatus]] = {
    RoundStatus.created: [
        RoundStatus.clarifying,
        RoundStatus.planning,       # skip clarification when no questions
    ],
    RoundStatus.clarifying: [
        RoundStatus.planning,
    ],
    RoundStatus.planning: [
        RoundStatus.coding,
    ],
    RoundStatus.coding: [
        RoundStatus.pr_created,
    ],
    RoundStatus.pr_created: [
        RoundStatus.reviewing,
    ],
    RoundStatus.reviewing: [
        RoundStatus.revising,
        RoundStatus.testing,
        RoundStatus.done,
    ],
    RoundStatus.revising: [
        RoundStatus.reviewing,
    ],
    RoundStatus.testing: [
        RoundStatus.done,
        RoundStatus.reviewing,      # test failure -> back to review cycle
    ],
    RoundStatus.done: [],            # terminal state
}


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class StateMachine:
    """Enforces valid Round status transitions.

    Usage::

        sm = StateMachine()
        sm.transition(RoundStatus.created, RoundStatus.clarifying)  # ok
        sm.transition(RoundStatus.done, RoundStatus.coding)         # raises
    """

    def transition(self, current: RoundStatus, target: RoundStatus) -> RoundStatus:
        """Validate and return *target* if the transition is allowed.

        Parameters
        ----------
        current:
            The current status of the Round.
        target:
            The desired next status.

        Returns
        -------
        RoundStatus
            The validated *target* status.

        Raises
        ------
        InvalidTransitionError
            If the transition is not in :data:`VALID_TRANSITIONS`.
        """
        allowed = VALID_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise InvalidTransitionError(current, target)
        return target

    def can_transition(self, current: RoundStatus, target: RoundStatus) -> bool:
        """Return ``True`` if the transition is allowed, ``False`` otherwise."""
        allowed = VALID_TRANSITIONS.get(current, [])
        return target in allowed

    def available_transitions(self, current: RoundStatus) -> list[RoundStatus]:
        """Return the list of statuses reachable from *current*."""
        return list(VALID_TRANSITIONS.get(current, []))
