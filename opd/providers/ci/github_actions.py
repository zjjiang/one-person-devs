"""GitHub Actions CI Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class GitHubActionsProvider(Provider):
    """CI provider using GitHub Actions (shares SCM token)."""

    CONFIG_SCHEMA = [
        {"name": "token", "label": "GitHub Token", "type": "password", "required": False},
    ]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="GitHub Actions provider 尚未实现")
