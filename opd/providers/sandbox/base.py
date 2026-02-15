"""Sandbox provider base class."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import HealthStatus, Provider


class SandboxProvider(Provider):
    """Abstract base for sandbox providers."""

    @abstractmethod
    async def create_sandbox(self, config: dict) -> dict:
        """Create a new sandbox environment."""

    @abstractmethod
    async def run_command(self, sandbox_id: str, command: str) -> dict:
        """Run a command inside a sandbox."""

    @abstractmethod
    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """Destroy a sandbox environment."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check if the sandbox provider is reachable."""
