"""iCode SCM Provider — 百度内部代码管理平台。"""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class ICodeProvider(Provider):
    """SCM provider for iCode (Baidu internal code hosting)."""

    CONFIG_SCHEMA = [
        {"name": "url", "label": "iCode 地址", "type": "text", "required": True},
        {"name": "token", "label": "Access Token", "type": "password", "required": True},
    ]

    async def health_check(self) -> HealthStatus:
        url = self.config.get("url")
        token = self.config.get("token")
        if not url or not token:
            return HealthStatus(healthy=False, message="缺少 iCode 地址或 Token")
        return HealthStatus(healthy=False, message="iCode provider 尚未实现")
