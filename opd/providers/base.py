"""Base provider abstraction for OPD."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Base class for all providers.

    Every provider receives a configuration dict at construction time
    and may optionally implement async ``initialize`` / ``cleanup``
    lifecycle hooks.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def initialize(self) -> None:
        """Optional async initialization hook.

        Called once after the provider instance is created and before it
        is used for the first time.  Subclasses may override this to
        open connections, validate credentials, etc.
        """

    async def cleanup(self) -> None:
        """Optional async cleanup hook.

        Called when the application is shutting down.  Subclasses may
        override this to close connections, flush buffers, etc.
        """
