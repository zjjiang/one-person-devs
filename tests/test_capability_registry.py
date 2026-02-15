"""Tests for the capability registry."""

import pytest

from opd.capabilities.base import Capability
from opd.capabilities.registry import CapabilityRegistry, PreflightResult

from conftest import UnhealthyProvider


class TestPreflightResult:
    def test_ok_when_no_errors(self):
        r = PreflightResult()
        assert r.ok is True

    def test_not_ok_with_errors(self):
        r = PreflightResult()
        r.add_error("missing ai")
        assert r.ok is False

    def test_warnings_dont_block(self):
        r = PreflightResult()
        r.add_warning("ci unavailable")
        assert r.ok is True


class TestCapabilityRegistry:
    @pytest.fixture
    def registry_with_unhealthy(self):
        reg = CapabilityRegistry()
        reg._capabilities["ai"] = Capability("ai", UnhealthyProvider())
        return reg

    async def test_preflight_passes_with_healthy(self, capability_registry):
        result = await capability_registry.preflight(["ai"])
        assert result.ok

    async def test_preflight_fails_missing_capability(self, capability_registry):
        result = await capability_registry.preflight(["nonexistent"])
        assert not result.ok
        assert any("nonexistent" in e for e in result.errors)

    async def test_preflight_fails_unhealthy(self, registry_with_unhealthy):
        result = await registry_with_unhealthy.preflight(["ai"])
        assert not result.ok

    async def test_optional_unhealthy_is_warning(self, registry_with_unhealthy):
        result = await registry_with_unhealthy.preflight([], ["ai"])
        assert result.ok
        assert len(result.warnings) == 1

    async def test_check_health(self, capability_registry):
        results = await capability_registry.check_health(["ai"])
        assert results["ai"].healthy is True

    async def test_check_health_missing(self, capability_registry):
        results = await capability_registry.check_health(["missing"])
        assert results["missing"].healthy is False

    def test_get_capability(self, capability_registry):
        assert capability_registry.get("ai") is not None
        assert capability_registry.get("nonexistent") is None
