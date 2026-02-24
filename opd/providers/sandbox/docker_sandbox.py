"""Docker Sandbox Provider."""

from __future__ import annotations

from opd.capabilities.base import HealthStatus, Provider


class DockerSandboxProvider(Provider):
    """Sandbox provider using Docker containers."""

    CONFIG_SCHEMA = [
        {"name": "host", "label": "Docker Host", "type": "text", "required": False,
         "default": "unix:///var/run/docker.sock"},
        {"name": "image", "label": "默认镜像", "type": "text", "required": False},
    ]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="Docker sandbox 尚未实现")
