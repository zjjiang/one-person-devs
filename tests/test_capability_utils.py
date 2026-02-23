"""Tests for capability_utils shared helpers."""

from __future__ import annotations

from opd.api.capability_utils import MASK, find_schema, mask_config, unmask_passwords


class TestFindSchema:
    def test_finds_matching_provider(self):
        available = [
            {
                "capability": "ai",
                "providers": [
                    {"name": "claude", "config_schema": [{"name": "api_key", "type": "password"}]},
                    {"name": "other", "config_schema": [{"name": "url", "type": "text"}]},
                ],
            }
        ]
        schema = find_schema(available, "ai", "claude")
        assert len(schema) == 1
        assert schema[0]["name"] == "api_key"

    def test_falls_back_to_first_provider(self):
        available = [
            {
                "capability": "ai",
                "providers": [
                    {"name": "claude", "config_schema": [{"name": "key"}]},
                ],
            }
        ]
        schema = find_schema(available, "ai", None)
        assert len(schema) == 1

    def test_returns_empty_for_unknown_capability(self):
        assert find_schema([], "unknown", None) == []

    def test_returns_empty_for_no_providers(self):
        available = [{"capability": "ai", "providers": []}]
        assert find_schema(available, "ai", None) == []


class TestMaskConfig:
    def test_masks_password_fields(self):
        config = {"api_key": "secret123", "model": "claude"}
        schema = [{"name": "api_key", "type": "password"}, {"name": "model", "type": "text"}]
        result = mask_config(config, schema)
        assert result["api_key"] == MASK
        assert result["model"] == "claude"

    def test_empty_password_not_masked(self):
        config = {"api_key": "", "model": "claude"}
        schema = [{"name": "api_key", "type": "password"}]
        result = mask_config(config, schema)
        assert result["api_key"] == ""

    def test_none_config_returns_empty(self):
        assert mask_config(None, []) == {}

    def test_no_password_fields(self):
        config = {"url": "http://example.com"}
        schema = [{"name": "url", "type": "text"}]
        result = mask_config(config, schema)
        assert result == config


class TestUnmaskPasswords:
    def test_replaces_mask_with_saved(self):
        config = {"api_key": MASK, "model": "claude"}
        saved = {"api_key": "real_secret"}
        schema = [{"name": "api_key", "type": "password"}]
        result = unmask_passwords(config, saved, schema)
        assert result["api_key"] == "real_secret"
        assert result["model"] == "claude"

    def test_keeps_new_value_if_not_masked(self):
        config = {"api_key": "new_key"}
        saved = {"api_key": "old_key"}
        schema = [{"name": "api_key", "type": "password"}]
        result = unmask_passwords(config, saved, schema)
        assert result["api_key"] == "new_key"

    def test_no_saved_config(self):
        config = {"api_key": MASK}
        schema = [{"name": "api_key", "type": "password"}]
        result = unmask_passwords(config, None, schema)
        assert result["api_key"] == MASK

    def test_does_not_mutate_input(self):
        config = {"api_key": MASK}
        saved = {"api_key": "secret"}
        schema = [{"name": "api_key", "type": "password"}]
        unmask_passwords(config, saved, schema)
        assert config["api_key"] == MASK  # original unchanged
