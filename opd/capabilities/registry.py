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

    # --- Project-level overrides ---

    def list_available(self) -> list[dict]:
        """Return all capability categories, their available providers, and CONFIG_SCHEMA."""
        result = []
        all_categories: dict[str, dict[str, str]] = {}
        # Merge built-in and external providers
        for cat, providers in _BUILTIN_PROVIDERS.items():
            all_categories.setdefault(cat, {}).update(providers)
        for cat, providers in self._external_providers.items():
            for pname, cls in providers.items():
                all_categories.setdefault(cat, {})[pname] = cls

        for category, providers in all_categories.items():
            provider_list = []
            for pname, dotted_or_cls in providers.items():
                schema = []
                try:
                    if isinstance(dotted_or_cls, str):
                        cls = _import_provider(dotted_or_cls)
                    else:
                        cls = dotted_or_cls
                    schema = getattr(cls, "CONFIG_SCHEMA", [])
                except Exception:
                    pass
                provider_list.append({"name": pname, "config_schema": schema})
            # Current active provider for this category
            active_cap = self._capabilities.get(category)
            result.append({
                "capability": category,
                "providers": provider_list,
                "active_provider": (
                    type(active_cap.provider).__name__ if active_cap else None
                ),
            })
        return result

    def create_temp_provider(self, category: str, provider_name: str,
                             config: dict) -> Provider | None:
        """Create a temporary (non-registered) provider instance for testing."""
        return self._create_provider(category, provider_name, config)

    async def with_project_overrides(
        self, project_configs: list[dict],
    ) -> CapabilityRegistry:
        """Return a new registry with project-level config overrides applied.

        project_configs: list of dicts with keys: capability, enabled,
                         provider_override, config_override.
        """
        new_reg = CapabilityRegistry()
        new_reg._external_providers = self._external_providers
        # Start with a copy of current capabilities
        new_reg._capabilities = dict(self._capabilities)

        for pc in project_configs:
            cap_name = pc["capability"]
            if not pc.get("enabled", True):
                new_reg._capabilities.pop(cap_name, None)
                continue

            provider_name = pc.get("provider_override")
            config_override = pc.get("config_override") or {}
            if not provider_name and not config_override:
                continue

            # Determine the provider name to use
            if not provider_name:
                existing = self._capabilities.get(cap_name)
                if not existing:
                    continue
                # Merge config_override into existing provider config
                merged = {**existing.provider.config, **config_override}
                provider = self._create_provider(
                    cap_name,
                    self._resolve_provider_name(cap_name, existing.provider),
                    merged,
                )
            else:
                # Use the overridden provider with merged config
                existing = self._capabilities.get(cap_name)
                base_config = existing.provider.config if existing else {}
                merged = {**base_config, **config_override}
                provider = self._create_provider(cap_name, provider_name, merged)

            if provider:
                await provider.initialize()
                new_reg._capabilities[cap_name] = Capability(cap_name, provider)

        return new_reg

    def _resolve_provider_name(self, category: str, provider: Provider) -> str:
        """Resolve the provider name from a provider instance."""
        cls_name = type(provider).__name__
        for pname, dotted in _BUILTIN_PROVIDERS.get(category, {}).items():
            if dotted.endswith(f":{cls_name}"):
                return pname
        return ""
