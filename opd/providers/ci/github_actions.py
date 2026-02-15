"""GitHub Actions CI provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus

from .base import CIProvider


class GitHubActionsProvider(CIProvider):
    """GitHub Actions CI provider (stub)."""

    async def trigger_pipeline(self, repo_url: str, branch: str) -> dict:
        raise NotImplementedError

    async def get_pipeline_status(self, pipeline_id: str) -> dict:
        raise NotImplementedError

    async def get_pipeline_logs(self, pipeline_id: str) -> str:
        raise NotImplementedError

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="Not implemented yet")
