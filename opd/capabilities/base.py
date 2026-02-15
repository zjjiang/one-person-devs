"""Capability system: abstraction layer for external dependencies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class HealthStatus:
    """Result of a capability health check."""

    healthy: bool
    message: str = ""
    latency_ms: int = 0
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Provider(ABC):
    """Base class for all provider implementations."""

    # Subclasses declare their config schema as a list of field descriptors.
    # Each entry: {"name": str, "label": str, "type": "string"|"password"|"select",
    #              "required": bool, "default": ..., "options": [...]}
    CONFIG_SCHEMA: list[dict] = []

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def initialize(self):
        """Called once after construction. Override for setup logic."""

    async def cleanup(self):
        """Called on shutdown. Override for teardown logic."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check if this provider is healthy and reachable."""


class Capability:
    """A named capability backed by a provider instance.

    Capabilities are the bridge between stages (which declare what they need)
    and providers (which implement the actual functionality).
    """

    def __init__(self, name: str, provider: Provider):
        self.name = name
        self.provider = provider
        self._last_health: HealthStatus | None = None

    def is_configured(self) -> bool:
        return self.provider is not None

    async def health_check(self) -> HealthStatus:
        self._last_health = await self.provider.health_check()
        return self._last_health

    @property
    def last_health(self) -> HealthStatus | None:
        return self._last_health
