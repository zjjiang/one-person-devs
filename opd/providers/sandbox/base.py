"""Abstract base class for sandbox providers."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from opd.providers.base import Provider


class SandboxProvider(Provider):
    """Interface for creating and managing isolated execution environments.

    A *sandbox* is a short-lived environment (container, VM, etc.) where
    build / test commands can be executed safely.
    """

    @abstractmethod
    async def create_sandbox(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a new sandbox and return its metadata.

        The returned dict must contain at least:

        - ``sandbox_id`` -- unique identifier for the sandbox
        - ``status`` -- current status (e.g. ``running``)
        """

    @abstractmethod
    async def run_command(
        self, sandbox_id: str, command: str
    ) -> dict[str, Any]:
        """Execute *command* inside the sandbox.

        Returns a dict with at least:

        - ``exit_code`` -- integer exit code
        - ``stdout`` -- captured standard output
        - ``stderr`` -- captured standard error
        """

    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """Tear down and remove the sandbox."""

    @abstractmethod
    async def get_logs(self, sandbox_id: str) -> str:
        """Return the full log output of the sandbox."""
