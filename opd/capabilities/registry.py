"""Capability registry: manages provider instances and project-level overrides."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field

from opd.capabilities.base import Capability, HealthStatus, Provider
from opd.config import CapabilityConfig

logger = logging.getLogger(__name__)

# Built-in provider implementations (lazy-imported on first use)
_BUILTIN_PROVIDERS: dict[str, dict[str, str]] = {
    "ai": {
        "claude_code": "opd.providers.ai.claude_code:ClaudeCodeProvider",
    },
    "scm": {
        "github": "opd.providers.scm.github:GitHubProvider",
    },
    "ci": {
        "github_actions": "opd.providers.ci.github_actions:GitHubActionsProvider",
    },
    "doc": {
        "local": "opd.providers.doc.local:LocalDocProvider",
        "notion": "opd.providers.doc.notion:NotionDocProvider",
    },
    "sandbox": {
        "docker_local": "opd.providers.sandbox.docker_local:DockerLocalProvider",
    },
    "notification": {
        "web": "opd.providers.notification.web:WebNotificationProvider",
    },
}


def _import_provider(dotted_path: str) -> type[Provider]:
    """Import a provider class from a dotted path like 'module.path:ClassName'."""
    module_path, class_name = dotted_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@dataclass
class PreflightResult:
    """Result of a preflight capability check before stage execution."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class CapabilityRegistry:
    """Manages capability instances and their providers."""

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}
        self._external_providers: dict[str, dict[str, type[Provider]]] = {}

    def register_provider(self, category: str, name: str, cls: type[Provider]):
        """Register an external provider implementation."""
        self._external_providers.setdefault(category, {})[name] = cls

    async def initialize_from_config(self, configs: dict[str, CapabilityConfig]):
        """Create and initialize capabilities from global config."""
        for cap_name, cap_config in configs.items():
            provider = self._create_provider(cap_name, cap_config.provider, cap_config.config)
            if provider:
                await provider.initialize()
                self._capabilities[cap_name] = Capability(cap_name, provider)
                logger.info("Capability [%s] initialized with provider [%s]", cap_name,
                            cap_config.provider)
            else:
                logger.warning("Capability [%s] provider [%s] not found, skipping",
                               cap_name, cap_config.provider)

    def _create_provider(self, category: str, provider_name: str,
                         config: dict) -> Provider | None:
        """Create a provider instance by category and name."""
        # Check external registrations first
        ext = self._external_providers.get(category, {}).get(provider_name)
        if ext:
            return ext(config)

        # Then check built-in providers
        builtin = _BUILTIN_PROVIDERS.get(category, {}).get(provider_name)
        if builtin:
            try:
                cls = _import_provider(builtin)
                return cls(config)
            except (ImportError, AttributeError) as e:
                logger.warning("Failed to import provider %s: %s", builtin, e)
                return None

        return None

    def get(self, name: str) -> Capability | None:
        """Get a capability by name."""
        return self._capabilities.get(name)

    async def check_health(self, cap_names: list[str]) -> dict[str, HealthStatus]:
        """Check health of multiple capabilities."""
        results = {}
        for name in cap_names:
            cap = self._capabilities.get(name)
            if cap:
                results[name] = await cap.health_check()
            else:
                results[name] = HealthStatus(healthy=False, message=f"Capability [{name}] not configured")
        return results

    async def preflight(self, required: list[str],
                        optional: list[str] | None = None) -> PreflightResult:
        """Run preflight checks for a stage's capability requirements."""
        result = PreflightResult()

        for name in required:
            cap = self._capabilities.get(name)
            if not cap:
                result.add_error(f"能力 [{name}] 未配��")
                continue
            health = await cap.health_check()
            if not health.healthy:
                result.add_error(f"能力 [{name}] 不可用: {health.message}")

        for name in (optional or []):
            cap = self._capabilities.get(name)
            if cap:
                health = await cap.health_check()
                if not health.healthy:
                    result.add_warning(f"能力 [{name}] 不可用，将降级处理: {health.message}")

        return result

    async def cleanup(self):
        """Cleanup all providers on shutdown."""
        for cap in self._capabilities.values():
            try:
                await cap.provider.cleanup()
            except Exception as e:
                logger.error("Error cleaning up capability [%s]: %s", cap.name, e)
