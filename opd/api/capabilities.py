"""Capabilities configuration API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.capability_utils import (
    HIDDEN_CAPABILITIES, find_schema, mask_config, unmask_passwords,
)
from opd.api.deps import get_db, get_orch
from opd.capabilities.registry import _PROVIDER_LABELS
from opd.db.models import GlobalCapabilityConfig, ProjectCapabilityConfig
from opd.engine.orchestrator import Orchestrator
from opd.models.schemas import SaveCapabilityConfigRequest, TestCapabilityRequest

router = APIRouter(prefix="/api/projects/{project_id}/capabilities", tags=["capabilities"])
catalog_router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


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
        schema = find_schema(available, cap_name, provider_name)
        items.append({
            "capability": cap_name,
            "providers": cap["providers"],
            "saved": {
                "enabled": sc.enabled if sc else True,
                "provider_override": sc.provider_override if sc else None,
                "config_override": mask_config(
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
        schema = find_schema(available, capability, body.provider_override)
        config_override = unmask_passwords(config_override, existing.config_override, schema)

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
    await db.flush()
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
        schema = find_schema(available, capability, body.provider)
        config = unmask_passwords(config, saved.config_override, schema)

    # Inject project repo_url for SCM providers to test repo access
    from opd.db.models import Project
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project and project.repo_url:
        config.setdefault("repo_url", project.repo_url)

    provider = orch.capabilities.create_temp_provider(capability, body.provider, config)
    if not provider:
        return {"healthy": False, "message": f"Provider [{body.provider}] not found"}

    await provider.initialize()
    try:
        status = await provider.health_check()
        return {"healthy": status.healthy, "message": status.message}
    finally:
        await provider.cleanup()


# --- Global catalog (no project_id needed) ---


@catalog_router.get("/catalog")
async def get_catalog(
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Return saved global capabilities for project creation form."""
    available = orch.capabilities.list_available()

    result = await db.execute(select(GlobalCapabilityConfig))
    rows = result.scalars().all()

    items = []
    for row in rows:
        if row.capability in HIDDEN_CAPABILITIES:
            continue
        schema = find_schema(available, row.capability, row.provider)
        items.append({
            "id": row.id,
            "capability": row.capability,
            "label": row.label or row.capability,
            "provider": row.provider,
            "provider_label": _PROVIDER_LABELS.get(row.provider, row.provider),
            "config_schema": schema,
            "enabled": row.enabled,
        })
    return items


# --- Batch save capabilities ---

@router.post("/batch")
async def batch_save_capabilities(
    project_id: int,
    body: list[SaveCapabilityConfigRequest],
    db: AsyncSession = Depends(get_db),
):
    """Batch upsert capability configs for a project (used after creation)."""
    for item in body:
        if not item.capability:
            continue
        result = await db.execute(
            select(ProjectCapabilityConfig).where(
                ProjectCapabilityConfig.project_id == project_id,
                ProjectCapabilityConfig.capability == item.capability,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.enabled = item.enabled
            existing.provider_override = item.provider_override
            existing.config_override = item.config_override or {}
        else:
            db.add(ProjectCapabilityConfig(
                project_id=project_id,
                capability=item.capability,
                enabled=item.enabled,
                provider_override=item.provider_override,
                config_override=item.config_override or {},
            ))
    await db.flush()
    return {"ok": True}
