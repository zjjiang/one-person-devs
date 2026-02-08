"""Provider registry with factory pattern and auto-discovery."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Type

from opd.providers.base import Provider

logger = logging.getLogger(__name__)

# Mapping of (category, type_name) -> fully-qualified class path for
# built-in providers.  This avoids importing every provider at module
# load time while still supporting auto-discovery.
_BUILTIN_PROVIDERS: dict[tuple[str, str], str] = {
    ("requirement", "local"): "opd.providers.requirement.local.LocalRequirementProvider",
    ("document", "local"): "opd.providers.document.local.LocalDocumentProvider",
    ("scm", "github"): "opd.providers.scm.github.GitHubSCMProvider",
    ("ai", "claude_code"): "opd.providers.ai.claude_code.ClaudeCodeAIProvider",
    ("notification", "web"): "opd.providers.notification.web.WebNotificationProvider",
}


def _import_class(dotted_path: str) -> Type[Provider]:
    """Import a class from a dotted module path like 'pkg.mod.Class'."""
    module_path, _, class_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class ProviderRegistry:
    """Central registry that maps (category, type_name) pairs to provider classes.

    Usage::

        registry = ProviderRegistry()
        # Register an external / third-party provider
        registry.register("scm", "gitlab", GitLabSCMProvider)
        # Create a provider instance from config
        provider = await registry.create("scm", "github", {"token": "..."})
    """

    def __init__(self) -> None:
        # Eagerly copy the built-in table so mutations don't affect the
        # module-level constant.
        self._providers: dict[tuple[str, str], Type[Provider] | str] = dict(_BUILTIN_PROVIDERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        category: str,
        type_name: str,
        provider_class: Type[Provider],
    ) -> None:
        """Register a provider class under *category* / *type_name*.

        This is the main extension point for external plugins.  If a
        built-in provider is already registered under the same key it
        will be replaced.
        """
        key = (category, type_name)
        if key in self._providers:
            logger.info(
                "Overriding provider %s/%s with %s",
                category,
                type_name,
                provider_class.__name__,
            )
        self._providers[key] = provider_class

    async def create(
        self,
        category: str,
        type_name: str,
        config: dict[str, Any] | None = None,
    ) -> Provider:
        """Instantiate, initialize, and return a provider.

        Raises ``KeyError`` if no provider is registered for the given
        *category* / *type_name* combination.
        """
        key = (category, type_name)
        entry = self._providers.get(key)
        if entry is None:
            available = [
                f"{c}/{t}" for c, t in sorted(self._providers.keys()) if c == category
            ]
            raise KeyError(
                f"No provider registered for {category}/{type_name}. "
                f"Available: {available or 'none'}"
            )

        # Lazy-import built-in providers stored as dotted-path strings.
        if isinstance(entry, str):
            cls = _import_class(entry)
            self._providers[key] = cls
        else:
            cls = entry

        instance = cls(config or {})
        await instance.initialize()
        return instance

    def list_providers(self, category: str | None = None) -> list[tuple[str, str]]:
        """Return registered (category, type_name) pairs.

        If *category* is given, only entries for that category are
        returned.
        """
        keys = sorted(self._providers.keys())
        if category is not None:
            keys = [(c, t) for c, t in keys if c == category]
        return keys
