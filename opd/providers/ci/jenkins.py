"""Jenkins CI Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class JenkinsProvider(Provider):
    """CI provider for Jenkins."""

    CONFIG_SCHEMA = [
        {"name": "url", "label": "Jenkins URL", "type": "text", "required": True},
        {"name": "user", "label": "用户名", "type": "text", "required": True},
        {"name": "token", "label": "API Token", "type": "password", "required": True},
    ]

    async def health_check(self) -> HealthStatus:
        url = self.config.get("url")
        if not url:
            return HealthStatus(healthy=False, message="缺少 Jenkins URL")
        return HealthStatus(healthy=False, message="Jenkins provider 尚未实现")
