"""CI provider base class."""

from __future__ import annotations

from abc import abstractmethod

from opd.capabilities.base import HealthStatus, Provider


class CIProvider(Provider):
    """Abstract base for CI/CD providers."""

    @abstractmethod
    async def trigger_pipeline(self, repo_url: str, branch: str) -> dict:
        """Trigger a CI pipeline run."""

    @abstractmethod
    async def get_pipeline_status(self, pipeline_id: str) -> dict:
        """Get the status of a pipeline run."""

    @abstractmethod
    async def get_pipeline_logs(self, pipeline_id: str) -> str:
        """Get logs from a pipeline run."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check if the CI provider is reachable."""
