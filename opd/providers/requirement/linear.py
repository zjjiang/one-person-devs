"""Linear Requirement Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class LinearProvider(Provider):
    """Requirement management provider for Linear."""

    CONFIG_SCHEMA = [
        {"name": "api_key", "label": "API Key", "type": "password", "required": True},
    ]

    async def health_check(self) -> HealthStatus:
        key = self.config.get("api_key")
        if not key:
            return HealthStatus(healthy=False, message="缺少 API Key")
        return HealthStatus(healthy=False, message="Linear provider 尚未实现")
