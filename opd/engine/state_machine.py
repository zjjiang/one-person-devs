"""State machine for Story status transitions."""

from __future__ import annotations

from opd.db.models import StoryStatus

VALID_TRANSITIONS: dict[str, list[str]] = {
    StoryStatus.preparing: [StoryStatus.clarifying],
    StoryStatus.clarifying: [StoryStatus.planning],
    StoryStatus.planning: [StoryStatus.designing],
    StoryStatus.designing: [StoryStatus.coding],
    StoryStatus.coding: [StoryStatus.verifying],
    StoryStatus.verifying: [StoryStatus.done, StoryStatus.coding, StoryStatus.designing],
}

ROLLBACK_ACTIONS: dict[tuple[str, str], str] = {
    (StoryStatus.verifying, StoryStatus.coding): "iterate",
    (StoryStatus.verifying, StoryStatus.designing): "restart",
}


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
        from_status = story.status if isinstance(story.status, str) else story.status.value
        to_value = to_status if isinstance(to_status, str) else to_status.value

        if not self.can_transition(from_status, to_value):
            raise InvalidTransitionError(from_status, to_value)

        story.status = to_status
        return ROLLBACK_ACTIONS.get((from_status, to_value))

    def available_transitions(self, status: str) -> list[str]:
        return VALID_TRANSITIONS.get(status, [])
