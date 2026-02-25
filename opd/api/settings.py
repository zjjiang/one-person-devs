"""Global settings API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.capability_utils import (
    HIDDEN_CAPABILITIES, find_schema, mask_config, unmask_passwords,
)
from opd.api.deps import get_db, get_orch
from opd.capabilities.registry import _CAPABILITY_LABELS, _PROVIDER_LABELS
from opd.db.models import GlobalCapabilityConfig
from opd.engine.orchestrator import Orchestrator
from opd.models.schemas import (
    CreateGlobalCapabilityRequest,
    SaveGlobalCapabilityRequest,
    TestGlobalCapabilityRequest,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/capabilities")
async def get_global_capabilities(
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Return only saved (DB) capability rows, enriched with config_schema."""
    available = orch.capabilities.list_available()

    result = await db.execute(select(GlobalCapabilityConfig))
    rows = result.scalars().all()

    items = []
    for row in rows:
        schema = find_schema(available, row.capability, row.provider)
        items.append({
            "id": row.id,
            "capability": row.capability,
            "provider": row.provider,
            "provider_label": _PROVIDER_LABELS.get(row.provider, row.provider),
            "label": row.label or _CAPABILITY_LABELS.get(row.capability, row.capability),
            "config_schema": schema,
            "enabled": row.enabled,
            "config": mask_config(row.config, schema),
        })
    return items


@router.get("/capabilities/available")
async def get_available_capabilities(
    orch: Orchestrator = Depends(get_orch),
):
    """Return builtin (capability, provider) pairs for the 'add' modal."""
    available = orch.capabilities.list_available()
    items = []
    for cap in available:
        cap_name = cap["capability"]
        if cap_name in HIDDEN_CAPABILITIES:
            continue
        label = cap.get("label", cap_name)
        for p in cap["providers"]:
            items.append({
                "capability": cap_name,
                "label": label,
                "provider": p["name"],
                "provider_label": p.get("label", p["name"]),
                "config_schema": p.get("config_schema", []),
            })
    return items


@router.post("/capabilities")
async def create_global_capability(
    body: CreateGlobalCapabilityRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Create a new global capability config row."""
    row = GlobalCapabilityConfig(
        capability=body.capability,
        provider=body.provider,
        enabled=body.enabled,
        label=body.label,
        config=body.config or {},
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "id": row.id}


@router.put("/capabilities/{config_id}")
async def save_global_capability(
    config_id: int,
    body: SaveGlobalCapabilityRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing global capability config by ID."""
    result = await db.execute(
        select(GlobalCapabilityConfig).where(GlobalCapabilityConfig.id == config_id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="能力配置不存在")

    config = body.config_override or {}
    if existing.config:
        available = orch.capabilities.list_available()
        schema = find_schema(available, existing.capability, existing.provider)
        config = unmask_passwords(config, existing.config, schema)

    existing.enabled = body.enabled
    existing.config = config
    if body.label is not None:
        existing.label = body.label
    await db.flush()
    return {"ok": True}


@router.post("/capabilities/{config_id}/test")
async def test_global_capability(
    config_id: int,
    body: TestGlobalCapabilityRequest,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Test a global capability config by ID."""
    result = await db.execute(
        select(GlobalCapabilityConfig).where(GlobalCapabilityConfig.id == config_id)
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="能力配置不存在")

    config = dict(body.config)
    if saved.config:
        available = orch.capabilities.list_available()
        schema = find_schema(available, saved.capability, saved.provider)
        config = unmask_passwords(config, saved.config, schema)

    prov = orch.capabilities.create_temp_provider(saved.capability, saved.provider, config)
    if not prov:
        return {"healthy": False, "message": f"Provider [{saved.provider}] not found"}

    await prov.initialize()
    try:
        status = await prov.health_check()
        return {"healthy": status.healthy, "message": status.message}
    finally:
        await prov.cleanup()


@router.post("/capabilities/verify-all")
async def verify_all_capabilities(
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Run health_check on all saved capability configs concurrently."""
    result = await db.execute(select(GlobalCapabilityConfig))
    rows = result.scalars().all()

    async def _check(row: GlobalCapabilityConfig) -> tuple[int, dict]:
        prov = orch.capabilities.create_temp_provider(row.capability, row.provider, row.config or {})
        if not prov:
            return row.id, {"healthy": False, "message": f"Provider [{row.provider}] not found"}
        await prov.initialize()
        try:
            status = await prov.health_check()
            return row.id, {"healthy": status.healthy, "message": status.message}
        except Exception as exc:
            return row.id, {"healthy": False, "message": str(exc)}
        finally:
            await prov.cleanup()

    checks = await asyncio.gather(*[_check(r) for r in rows], return_exceptions=True)
    results: dict[int, dict] = {}
    for item in checks:
        if isinstance(item, Exception):
            continue
        rid, status = item
        results[rid] = status
    return results


@router.delete("/capabilities/{config_id}")
async def delete_global_capability(
    config_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a global capability config row by ID."""
    result = await db.execute(
        select(GlobalCapabilityConfig).where(GlobalCapabilityConfig.id == config_id)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="能力配置不存在")
    await db.delete(existing)
    await db.flush()
    return {"ok": True}
