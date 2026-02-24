"""Jira Requirement Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class JiraProvider(Provider):
    """Requirement management provider for Jira."""

    CONFIG_SCHEMA = [
        {"name": "url", "label": "Jira URL", "type": "text", "required": True},
        {"name": "email", "label": "邮箱", "type": "text", "required": True},
        {"name": "token", "label": "API Token", "type": "password", "required": True},
    ]

    async def health_check(self) -> HealthStatus:
        url = self.config.get("url")
        if not url:
            return HealthStatus(healthy=False, message="缺少 Jira URL")
        return HealthStatus(healthy=False, message="Jira provider 尚未实现")
