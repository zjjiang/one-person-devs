"""Tests for build_capability_overrides helper."""

from __future__ import annotations

from types import SimpleNamespace

from opd.capabilities.registry import build_capability_overrides


class TestBuildCapabilityOverrides:
    def test_builds_override_dicts(self):
        configs = [
            SimpleNamespace(
                capability="ai", enabled=True,
                provider_override="claude", config_override={"key": "val"},
            ),
            SimpleNamespace(
                capability="scm", enabled=False,
                provider_override=None, config_override=None,
            ),
        ]
        result = build_capability_overrides(configs)
        assert len(result) == 2
        assert result[0] == {
            "capability": "ai", "enabled": True,
            "provider_override": "claude", "config_override": {"key": "val"},
        }
        assert result[1]["enabled"] is False

    def test_empty_list(self):
        assert build_capability_overrides([]) == []
