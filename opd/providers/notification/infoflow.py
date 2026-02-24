"""如流 (InfoFlow) Notification Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class InfoFlowProvider(Provider):
    """Notification provider for 如流 (InfoFlow)."""

    CONFIG_SCHEMA = [
        {"name": "webhook_url", "label": "Webhook URL", "type": "text", "required": True},
    ]

    async def health_check(self) -> HealthStatus:
        url = self.config.get("webhook_url")
        if not url:
            return HealthStatus(healthy=False, message="缺少 Webhook URL")
        return HealthStatus(healthy=False, message="如流 provider 尚未实现")
