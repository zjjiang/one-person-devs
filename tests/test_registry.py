"""Tests for CapabilityRegistry and PreflightResult."""

from __future__ import annotations



from opd.capabilities.base import Capability, HealthStatus, Provider
from opd.capabilities.registry import CapabilityRegistry, PreflightResult


class MockProvider(Provider):
    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, message="ok")


class UnhealthyProvider(Provider):
    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="down")


# ── PreflightResult ──


class TestPreflightResult:
    def test_ok_when_no_errors(self):
        r = PreflightResult()
        assert r.ok

    def test_not_ok_with_errors(self):
        r = PreflightResult()
        r.add_error("missing ai")
        assert not r.ok
        assert "missing ai" in r.errors

    def test_warnings_dont_affect_ok(self):
        r = PreflightResult()
        r.add_warning("optional missing")
        assert r.ok
        assert len(r.warnings) == 1


# ── CapabilityRegistry ──


class TestCapabilityRegistry:
    def test_get_returns_none_for_missing(self):
        reg = CapabilityRegistry()
        assert reg.get("nonexistent") is None

    def test_get_returns_capability(self):
        reg = CapabilityRegistry()
        cap = Capability("ai", MockProvider())
        reg._capabilities["ai"] = cap
        assert reg.get("ai") is cap

    def test_register_external_provider(self):
        reg = CapabilityRegistry()
        reg.register_provider("custom", "my_provider", MockProvider)
        assert "custom" in reg._external_providers
        assert "my_provider" in reg._external_providers["custom"]

    async def test_check_health_healthy(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", MockProvider())
        results = await reg.check_health(["ai"])
        assert results["ai"].healthy

    async def test_check_health_missing_cap(self):
        reg = CapabilityRegistry()
        results = await reg.check_health(["ai"])
        assert not results["ai"].healthy
        assert "not configured" in results["ai"].message

    async def test_check_health_unhealthy(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", UnhealthyProvider())
        results = await reg.check_health(["ai"])
        assert not results["ai"].healthy

    async def test_preflight_required_ok(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", MockProvider())
        result = await reg.preflight(required=["ai"])
        assert result.ok

    async def test_preflight_required_missing(self):
        reg = CapabilityRegistry()
        result = await reg.preflight(required=["ai"])
        assert not result.ok
        assert any("ai" in e for e in result.errors)

    async def test_preflight_required_unhealthy(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", UnhealthyProvider())
        result = await reg.preflight(required=["ai"])
        assert not result.ok

    async def test_preflight_optional_missing_is_ok(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", MockProvider())
        result = await reg.preflight(required=["ai"], optional=["scm"])
        assert result.ok  # optional missing doesn't cause error

    async def test_preflight_optional_unhealthy_warns(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", MockProvider())
        reg._capabilities["scm"] = Capability("scm", UnhealthyProvider())
        result = await reg.preflight(required=["ai"], optional=["scm"])
        assert result.ok
        assert len(result.warnings) == 1

    async def test_cleanup(self):
        cleaned = []

        class TrackingProvider(MockProvider):
            async def cleanup(self):
                cleaned.append(True)

        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", TrackingProvider())
        await reg.cleanup()
        assert len(cleaned) == 1

    async def test_cleanup_handles_errors(self):
        class FailingProvider(MockProvider):
            async def cleanup(self):
                raise RuntimeError("cleanup failed")

        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", FailingProvider())
        # Should not raise
        await reg.cleanup()

    def test_create_provider_external(self):
        reg = CapabilityRegistry()
        reg.register_provider("test", "mock", MockProvider)
        provider = reg._create_provider("test", "mock", {})
        assert isinstance(provider, MockProvider)

    def test_create_provider_unknown(self):
        reg = CapabilityRegistry()
        assert reg._create_provider("unknown", "nope", {}) is None

    def test_create_temp_provider(self):
        reg = CapabilityRegistry()
        reg.register_provider("test", "mock", MockProvider)
        provider = reg.create_temp_provider("test", "mock", {})
        assert isinstance(provider, MockProvider)

    def test_list_available(self):
        reg = CapabilityRegistry()
        available = reg.list_available()
        # Should include built-in categories
        categories = [a["capability"] for a in available]
        assert "ai" in categories
        assert "scm" in categories

    def test_list_available_includes_external(self):
        reg = CapabilityRegistry()
        reg.register_provider("custom", "my_prov", MockProvider)
        available = reg.list_available()
        categories = [a["capability"] for a in available]
        assert "custom" in categories

    async def test_initialize_from_config(self):
        from opd.config import CapabilityConfig

        reg = CapabilityRegistry()
        reg.register_provider("test", "mock", MockProvider)
        configs = {"test": CapabilityConfig(provider="mock", config={})}
        await reg.initialize_from_config(configs)
        assert reg.get("test") is not None

    async def test_initialize_from_config_unknown_provider(self):
        from opd.config import CapabilityConfig

        reg = CapabilityRegistry()
        configs = {"test": CapabilityConfig(provider="nonexistent", config={})}
        await reg.initialize_from_config(configs)
        assert reg.get("test") is None

    def test_resolve_provider_name(self):
        reg = CapabilityRegistry()
        # Create a mock that looks like ClaudeCodeProvider
        class ClaudeCodeProvider(MockProvider):
            pass

        provider = ClaudeCodeProvider()
        name = reg.resolve_provider_name("ai", provider)
        assert name == "claude_code"

    def test_resolve_provider_name_unknown(self):
        reg = CapabilityRegistry()
        name = reg.resolve_provider_name("ai", MockProvider())
        assert name == ""
