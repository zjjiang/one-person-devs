"""Project management API routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.db.models import Project, WorkspaceStatus
from opd.db.session import get_session_factory
from opd.engine.orchestrator import Orchestrator
from opd.engine.workspace import clone_workspace
from opd.models.schemas import CreateProjectRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Track running clone tasks by project id
_clone_tasks: dict[int, asyncio.Task] = {}


def _launch_clone(project_id: int, repo_url: str) -> None:
    """Launch async git clone for a project."""
    if project_id in _clone_tasks:
        return  # Already running

    async def _run() -> None:
        await asyncio.sleep(0.3)  # Wait for request DB session to commit
        session_factory = get_session_factory()

        # Resolve SCM token from registry or global config
        token = await _resolve_scm_token(session_factory)
        logger.info("Clone project %s: token resolved = %s", project_id, bool(token))

        try:
            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = result.scalar_one_or_none()
                    if not project:
                        return
                    project.workspace_status = WorkspaceStatus.cloning
                    project.workspace_error = ""

            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = result.scalar_one_or_none()
                    if not project:
                        return
                    try:
                        await clone_workspace(project, repo_url, token=token)
                        project.workspace_status = WorkspaceStatus.ready
                        project.workspace_error = ""
                    except Exception as e:
                        logger.exception("Clone failed for project %s", project_id)
                        project.workspace_status = WorkspaceStatus.error
                        project.workspace_error = str(e)
        except Exception as e:
            logger.exception("Clone task crashed for project %s", project_id)
            try:
                async with session_factory() as db:
                    async with db.begin():
                        result = await db.execute(
                            select(Project).where(Project.id == project_id)
                        )
                        project = result.scalar_one_or_none()
                        if project:
                            project.workspace_status = WorkspaceStatus.error
                            project.workspace_error = str(e)
            except Exception:
                logger.exception("Failed to update error status for project %s", project_id)
        finally:
            _clone_tasks.pop(project_id, None)

    task = asyncio.create_task(_run())
    _clone_tasks[project_id] = task


async def _resolve_scm_token(session_factory) -> str | None:
    """Resolve SCM token from registry or GlobalCapabilityConfig."""
    import os
    from opd.db.models import GlobalCapabilityConfig
    from opd.main import get_orchestrator

    # 1) Try in-memory registry
    try:
        orch = get_orchestrator()
        scm_cap = orch.capabilities.get("scm")
        if scm_cap:
            token = scm_cap.provider.config.get("token")
            if token:
                return token
    except Exception:
        pass

    # 2) Try GlobalCapabilityConfig table
    try:
        async with session_factory() as db:
            result = await db.execute(
                select(GlobalCapabilityConfig)
                .where(GlobalCapabilityConfig.capability == "scm")
            )
            gc = result.scalar_one_or_none()
            if gc and gc.config:
                token = gc.config.get("token")
                if token:
                    return token
    except Exception:
        pass

    # 3) Fallback to env var
    return os.environ.get("GITHUB_TOKEN")


@router.post("")
async def create_project(req: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=req.name,
        repo_url=req.repo_url,
        description=req.description or "",
        tech_stack=req.tech_stack or "",
        architecture=req.architecture or "",
        workspace_dir=req.workspace_dir or "",
        workspace_status=WorkspaceStatus.pending,
    )
    db.add(project)
    await db.flush()
    _launch_clone(project.id, req.repo_url)
    return {"id": project.id, "name": project.name}


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).options(selectinload(Project.stories))
    )
    projects = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "repo_url": p.repo_url,
            "story_count": len(p.stories),
            "workspace_status": p.workspace_status.value,
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.rules),
            selectinload(Project.skills),
            selectinload(Project.stories),
            selectinload(Project.capability_configs),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "id": project.id,
        "name": project.name,
        "repo_url": project.repo_url,
        "description": project.description,
        "tech_stack": project.tech_stack,
        "architecture": project.architecture,
        "workspace_dir": project.workspace_dir,
        "workspace_status": project.workspace_status.value,
        "workspace_error": project.workspace_error,
        "rules": [
            {"id": r.id, "category": r.category.value, "content": r.content, "enabled": r.enabled}
            for r in project.rules
        ],
        "skills": [
            {"id": s.id, "name": s.name, "trigger": s.trigger.value}
            for s in project.skills
        ],
        "stories": [
            {"id": s.id, "title": s.title, "status": s.status.value}
            for s in project.stories
        ],
    }


@router.put("/{project_id}")
async def update_project(
    project_id: int, req: CreateProjectRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    old_repo_url = project.repo_url
    project.name = req.name
    project.repo_url = req.repo_url
    project.description = req.description or ""
    project.tech_stack = req.tech_stack or ""
    project.architecture = req.architecture or ""
    project.workspace_dir = req.workspace_dir or ""
    # Re-clone if repo_url changed
    if req.repo_url != old_repo_url:
        project.workspace_status = WorkspaceStatus.pending
        project.workspace_error = ""
        await db.flush()
        _launch_clone(project.id, req.repo_url)
    return {"id": project.id, "name": project.name}


@router.post("/{project_id}/init-workspace")
async def init_workspace(project_id: int, db: AsyncSession = Depends(get_db)):
    """Manually trigger workspace initialization."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.workspace_status == WorkspaceStatus.cloning:
        return {"status": "cloning", "message": "Clone already in progress"}
    project.workspace_status = WorkspaceStatus.pending
    project.workspace_error = ""
    await db.flush()
    _launch_clone(project_id, project.repo_url)
    return {"status": "cloning", "message": "Workspace initialization started"}


@router.get("/{project_id}/workspace-status")
async def workspace_status(project_id: int, db: AsyncSession = Depends(get_db)):
    """Query workspace initialization status."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "status": project.workspace_status.value,
        "error": project.workspace_error,
    }


@router.post("/verify-repo")
async def verify_repo(
    body: dict,
    orch: Orchestrator = Depends(get_orch),
    db: AsyncSession = Depends(get_db),
):
    """Verify repo access using the configured SCM provider."""
    repo_url = body.get("repo_url", "").strip()
    if not repo_url:
        return {"healthy": False, "message": "请输入仓库地址"}

    # 1) Try in-memory registry (from opd.yaml)
    scm_cap = orch.capabilities.get("scm")
    if scm_cap:
        config = {**scm_cap.provider.config, "repo_url": repo_url}
        provider_name = orch.capabilities._resolve_provider_name("scm", scm_cap.provider)
    else:
        # 2) Fallback: check GlobalCapabilityConfig table
        from opd.db.models import GlobalCapabilityConfig
        result = await db.execute(
            select(GlobalCapabilityConfig)
            .where(GlobalCapabilityConfig.capability == "scm")
        )
        gc = result.scalar_one_or_none()
        if not gc or not gc.provider:
            return {"healthy": False, "message": "SCM 能力未配置，请先在全局设置中配置"}
        config = {**(gc.config or {}), "repo_url": repo_url}
        provider_name = gc.provider

    provider = orch.capabilities.create_temp_provider("scm", provider_name, config)
    if not provider:
        return {"healthy": False, "message": "无法创建 SCM provider"}

    await provider.initialize()
    try:
        status = await provider.health_check()
        return {"healthy": status.healthy, "message": status.message}
    finally:
        await provider.cleanup()
