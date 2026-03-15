"""State machine for Story status transitions."""

from __future__ import annotations

from opd.db.models import StoryStatus


def ensure_status_value(status) -> str:
    """Extract string value from StoryStatus enum or pass through strings."""
    return status.value if not isinstance(status, str) else status

VALID_TRANSITIONS: dict[str, list[str]] = {
    StoryStatus.preparing: [StoryStatus.clarifying],
    StoryStatus.briefing: [StoryStatus.coding],
    StoryStatus.clarifying: [StoryStatus.planning, StoryStatus.preparing],
    StoryStatus.planning: [StoryStatus.designing, StoryStatus.preparing, StoryStatus.clarifying],
    StoryStatus.designing: [
        StoryStatus.coding, StoryStatus.preparing, StoryStatus.clarifying, StoryStatus.planning,
    ],
    StoryStatus.coding: [StoryStatus.verifying, StoryStatus.designing, StoryStatus.briefing],
    StoryStatus.verifying: [
        StoryStatus.done, StoryStatus.coding, StoryStatus.designing, StoryStatus.briefing,
    ],
}

ROLLBACK_ACTIONS: dict[tuple[str, str], str] = {
    (StoryStatus.verifying, StoryStatus.coding): "iterate",
    (StoryStatus.verifying, StoryStatus.designing): "restart",
    (StoryStatus.verifying, StoryStatus.briefing): "restart",
}

# Mode-aware "next status" mapping for confirm_stage.
# VALID_TRANSITIONS defines what's *possible*; this defines the *default next step* per mode.
MODE_NEXT_STATUS: dict[str, dict[str, str]] = {
    "full": {
        "preparing": "clarifying",
        "clarifying": "planning",
        "planning": "designing",
        "designing": "coding",
        "verifying": "done",
    },
    "light": {
        "briefing": "coding",
        "verifying": "done",
    },
}


def get_next_status(current: str, mode: str) -> str | None:
    """Return the default next status for a given stage and mode."""
    return MODE_NEXT_STATUS.get(mode, MODE_NEXT_STATUS["full"]).get(current)


class InvalidTransitionError(Exception):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition: {from_status} → {to_status}")


class StateMachine:
    """Validates and executes Story status transitions."""

    def can_transition(self, from_status: str, to_status: str) -> bool:
        return to_status in VALID_TRANSITIONS.get(from_status, [])

    def transition(self, story, to_status: str) -> str | None:
        """Transition a story to a new status. Returns rollback action if applicable."""
        from_status = ensure_status_value(story.status)
        to_value = ensure_status_value(to_status)

        if not self.can_transition(from_status, to_value):
            raise InvalidTransitionError(from_status, to_value)

        story.status = to_status
        return ROLLBACK_ACTIONS.get((from_status, to_value))

    def available_transitions(self, status: str) -> list[str]:
        return VALID_TRANSITIONS.get(status, [])
