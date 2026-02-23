"""Global settings API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.capability_utils import CAPABILITY_LABELS, find_schema, mask_config, unmask_passwords
from opd.api.deps import get_db, get_orch
from opd.db.models import GlobalCapabilityConfig
from opd.engine.orchestrator import Orchestrator
from opd.models.schemas import SaveCapabilityConfigRequest, TestCapabilityRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/capabilities")
async def get_global_capabilities(
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Get capability catalog merged with global saved configs."""
    available = orch.capabilities.list_available()

    result = await db.execute(select(GlobalCapabilityConfig))
    saved = {c.capability: c for c in result.scalars().all()}

    items = []
    for cap in available:
        cap_name = cap["capability"]
        sc = saved.get(cap_name)
        provider_name = sc.provider if sc else None
        schema = find_schema(available, cap_name, provider_name)
        items.append({
            "capability": cap_name,
            "label": CAPABILITY_LABELS.get(cap_name, cap_name),
            "providers": cap["providers"],
            "saved": {
                "enabled": sc.enabled if sc else True,
                "provider": sc.provider if sc else None,
                "config": mask_config(sc.config, schema) if sc else {},
            },
        })
    return items


@router.put("/capabilities/{capability}")
async def save_global_capability(
    capability: str,
    body: SaveCapabilityConfigRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Save global capability configuration."""
    result = await db.execute(
        select(GlobalCapabilityConfig)
        .where(GlobalCapabilityConfig.capability == capability)
    )
    existing = result.scalar_one_or_none()

    config = body.config_override or {}
    if existing and existing.config:
        available = orch.capabilities.list_available()
        schema = find_schema(available, capability, body.provider_override)
        config = unmask_passwords(config, existing.config, schema)

    if existing:
        existing.enabled = body.enabled
        existing.provider = body.provider_override
        existing.config = config
    else:
        db.add(GlobalCapabilityConfig(
            capability=capability,
            enabled=body.enabled,
            provider=body.provider_override,
            config=config,
        ))
    await db.flush()
    return {"ok": True}


@router.post("/capabilities/{capability}/test")
async def test_global_capability(
    capability: str,
    body: TestCapabilityRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Test a global capability config."""
    config = dict(body.config)
    result = await db.execute(
        select(GlobalCapabilityConfig)
        .where(GlobalCapabilityConfig.capability == capability)
    )
    saved = result.scalar_one_or_none()
    if saved and saved.config:
        available = orch.capabilities.list_available()
        schema = find_schema(available, capability, body.provider)
        config = unmask_passwords(config, saved.config, schema)

    provider = orch.capabilities.create_temp_provider(capability, body.provider, config)
    if not provider:
        return {"healthy": False, "message": f"Provider [{body.provider}] not found"}

    await provider.initialize()
    try:
        status = await provider.health_check()
        return {"healthy": status.healthy, "message": status.message}
    finally:
        await provider.cleanup()
