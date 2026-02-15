"""Capabilities configuration API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.deps import get_db, get_orch
from opd.db.models import ProjectCapabilityConfig
from opd.engine.orchestrator import Orchestrator
from opd.models.schemas import SaveCapabilityConfigRequest, TestCapabilityRequest

router = APIRouter(prefix="/api/projects/{project_id}/capabilities", tags=["capabilities"])

_MASK = "***"


def _mask_config(config: dict | None, schema: list[dict]) -> dict:
    """Mask password-type fields in config for API responses."""
    if not config:
        return {}
    password_fields = {f["name"] for f in schema if f.get("type") == "password"}
    masked = {}
    for k, v in config.items():
        masked[k] = _MASK if k in password_fields and v else v
    return masked


def _find_schema(available: list[dict], capability: str,
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


@router.get("")
async def get_capabilities(
    project_id: int,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Get capability catalog merged with project's saved configs."""
    available = orch.capabilities.list_available()

    # Load saved project configs
    result = await db.execute(
        select(ProjectCapabilityConfig)
        .where(ProjectCapabilityConfig.project_id == project_id)
    )
    saved = {c.capability: c for c in result.scalars().all()}

    items = []
    for cap in available:
        cap_name = cap["capability"]
        sc = saved.get(cap_name)
        # Determine which provider to use for schema lookup
        provider_name = sc.provider_override if sc else None
        schema = _find_schema(available, cap_name, provider_name)
        items.append({
            "capability": cap_name,
            "providers": cap["providers"],
            "saved": {
                "enabled": sc.enabled if sc else True,
                "provider_override": sc.provider_override if sc else None,
                "config_override": _mask_config(
                    sc.config_override, schema
                ) if sc else {},
            },
        })
    return items


@router.put("/{capability}")
async def save_capability_config(
    project_id: int,
    capability: str,
    body: SaveCapabilityConfigRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Upsert project capability configuration."""
    result = await db.execute(
        select(ProjectCapabilityConfig)
        .where(
            ProjectCapabilityConfig.project_id == project_id,
            ProjectCapabilityConfig.capability == capability,
        )
    )
    existing = result.scalar_one_or_none()

    # Resolve masked password fields: keep old values if user sent "***"
    config_override = body.config_override or {}
    if existing and existing.config_override:
        available = orch.capabilities.list_available()
        schema = _find_schema(available, capability, body.provider_override)
        password_fields = {f["name"] for f in schema if f.get("type") == "password"}
        for field_name in password_fields:
            if config_override.get(field_name) == _MASK:
                config_override[field_name] = existing.config_override.get(field_name)

    if existing:
        existing.enabled = body.enabled
        existing.provider_override = body.provider_override
        existing.config_override = config_override
    else:
        db.add(ProjectCapabilityConfig(
            project_id=project_id,
            capability=capability,
            enabled=body.enabled,
            provider_override=body.provider_override,
            config_override=config_override,
        ))
    await db.commit()
    return {"ok": True}


@router.post("/{capability}/test")
async def test_capability(
    project_id: int,
    capability: str,
    body: TestCapabilityRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Test a capability config by creating a temp provider and running health_check."""
    # Resolve masked password fields from saved config
    config = dict(body.config)
    result = await db.execute(
        select(ProjectCapabilityConfig)
        .where(
            ProjectCapabilityConfig.project_id == project_id,
            ProjectCapabilityConfig.capability == capability,
        )
    )
    saved = result.scalar_one_or_none()
    if saved and saved.config_override:
        available = orch.capabilities.list_available()
        schema = _find_schema(available, capability, body.provider)
        password_fields = {f["name"] for f in schema if f.get("type") == "password"}
        for field_name in password_fields:
            if config.get(field_name) == _MASK:
                config[field_name] = saved.config_override.get(field_name)

    provider = orch.capabilities.create_temp_provider(capability, body.provider, config)
    if not provider:
        return {"healthy": False, "message": f"Provider [{body.provider}] not found"}

    await provider.initialize()
    try:
        status = await provider.health_check()
        return {"healthy": status.healthy, "message": status.message}
    finally:
        await provider.cleanup()
