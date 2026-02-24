"""Shared helpers for capability configuration API endpoints."""

from __future__ import annotations

MASK = "***"

HIDDEN_CAPABILITIES: set[str] = {"doc"}


def find_schema(available: list[dict], capability: str,
                provider_name: str | None) -> list[dict]:
    """Find CONFIG_SCHEMA for a given capability/provider."""
    for cap in available:
        if cap["capability"] == capability:
            for p in cap["providers"]:
                if provider_name and p["name"] == provider_name:
                    return p.get("config_schema", [])
            # Return first provider's schema as fallback
            if cap["providers"]:
                return cap["providers"][0].get("config_schema", [])
    return []


def mask_config(config: dict | None, schema: list[dict]) -> dict:
    """Mask password-type fields in config for API responses."""
    if not config:
        return {}
    password_fields = {f["name"] for f in schema if f.get("type") == "password"}
    return {k: (MASK if k in password_fields and v else v) for k, v in config.items()}


def unmask_passwords(
    config: dict, saved_config: dict | None, schema: list[dict],
) -> dict:
    """Replace masked password values with saved originals."""
    if not saved_config:
        return config
    password_fields = {f["name"] for f in schema if f.get("type") == "password"}
    result = dict(config)
    for field_name in password_fields:
        if result.get(field_name) == MASK:
            result[field_name] = saved_config.get(field_name)
    return result
