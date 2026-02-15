"""Docker-based local sandbox provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus

from .base import SandboxProvider


class DockerLocalProvider(SandboxProvider):
    """Local Docker sandbox provider (stub)."""

    CONFIG_SCHEMA = []

    async def create_sandbox(self, config: dict) -> dict:
        raise NotImplementedError

    async def run_command(self, sandbox_id: str, command: str) -> dict:
        raise NotImplementedError

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        raise NotImplementedError

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="Not implemented yet")
