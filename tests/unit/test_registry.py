"""Unit tests for opd.providers.registry."""

from __future__ import annotations

from typing import Any

import pytest

from opd.providers.base import Provider
from opd.providers.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# Mock provider for testing
# ---------------------------------------------------------------------------

class MockProvider(Provider):
    """A simple mock provider for registry tests."""

    initialized: bool = False

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True


class AnotherMockProvider(Provider):
    """A second mock provider to test overrides."""

    async def initialize(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Return a fresh ProviderRegistry instance."""
    return ProviderRegistry()


@pytest.fixture
def empty_registry():
    """Return a registry with no built-in providers."""
    reg = ProviderRegistry()
    reg._providers.clear()
    return reg


# ---------------------------------------------------------------------------
# Tests for register
# ---------------------------------------------------------------------------

class TestRegister:
    """Tests for ProviderRegistry.register."""

    def test_register_new_provider(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        assert ("scm", "mock") in empty_registry._providers
        assert empty_registry._providers[("scm", "mock")] is MockProvider

    def test_register_overwrites_existing(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        empty_registry.register("scm", "mock", AnotherMockProvider)
        assert empty_registry._providers[("scm", "mock")] is AnotherMockProvider

    def test_register_multiple_categories(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        empty_registry.register("ai", "mock", AnotherMockProvider)
        assert ("scm", "mock") in empty_registry._providers
        assert ("ai", "mock") in empty_registry._providers

    def test_register_does_not_affect_builtin_constant(self, registry):
        """Registering should not mutate the module-level _BUILTIN_PROVIDERS."""
        from opd.providers.registry import _BUILTIN_PROVIDERS
        original_keys = set(_BUILTIN_PROVIDERS.keys())
        registry.register("custom", "test", MockProvider)
        assert set(_BUILTIN_PROVIDERS.keys()) == original_keys


# ---------------------------------------------------------------------------
# Tests for create
# ---------------------------------------------------------------------------

class TestCreate:
    """Tests for ProviderRegistry.create."""

    async def test_create_returns_initialized_provider(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        provider = await empty_registry.create("scm", "mock", {"key": "val"})
        assert isinstance(provider, MockProvider)
        assert provider.initialized is True
        assert provider.config == {"key": "val"}

    async def test_create_with_no_config(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        provider = await empty_registry.create("scm", "mock")
        assert provider.config == {}

    async def test_create_unknown_raises_key_error(self, empty_registry):
        with pytest.raises(KeyError, match="No provider registered"):
            await empty_registry.create("scm", "nonexistent")

    async def test_create_unknown_shows_available(self, empty_registry):
        empty_registry.register("scm", "mock", MockProvider)
        with pytest.raises(KeyError, match="scm/mock"):
            await empty_registry.create("scm", "nonexistent")

    async def test_create_empty_category_shows_none(self, empty_registry):
        with pytest.raises(KeyError, match="none"):
            await empty_registry.create("scm", "nonexistent")


# ---------------------------------------------------------------------------
# Tests for list_providers
# ---------------------------------------------------------------------------

class TestListProviders:
    """Tests for ProviderRegistry.list_providers."""

    def test_list_all_providers(self, empty_registry):
        empty_registry.register("scm", "github", MockProvider)
        empty_registry.register("ai", "claude", AnotherMockProvider)
        result = empty_registry.list_providers()
        assert ("scm", "github") in result
        assert ("ai", "claude") in result

    def test_list_filtered_by_category(self, empty_registry):
        empty_registry.register("scm", "github", MockProvider)
        empty_registry.register("scm", "gitlab", AnotherMockProvider)
        empty_registry.register("ai", "claude", MockProvider)
        result = empty_registry.list_providers(category="scm")
        assert len(result) == 2
        assert all(c == "scm" for c, _ in result)

    def test_list_empty_category(self, empty_registry):
        empty_registry.register("scm", "github", MockProvider)
        result = empty_registry.list_providers(category="ai")
        assert result == []

    def test_list_empty_registry(self, empty_registry):
        result = empty_registry.list_providers()
        assert result == []

    def test_list_returns_sorted(self, empty_registry):
        empty_registry.register("scm", "gitlab", MockProvider)
        empty_registry.register("ai", "claude", MockProvider)
        empty_registry.register("scm", "github", MockProvider)
        result = empty_registry.list_providers()
        assert result == sorted(result)

    def test_builtin_providers_listed(self, registry):
        """The default registry should list built-in providers."""
        result = registry.list_providers()
        assert len(result) > 0
        # Check that known built-ins are present
        assert ("scm", "github") in result
        assert ("ai", "claude_code") in result
