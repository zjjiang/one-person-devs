"""Project management API routes."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db, get_orch
from opd.capabilities.registry import _CAPABILITY_LABELS, _PROVIDER_LABELS
from opd.db.models import (
    GlobalCapabilityConfig,
    Project,
    ProjectCapabilityConfig,
    WorkspaceStatus,
)
from opd.db.session import get_session_factory
from opd.engine.orchestrator import Orchestrator
from opd.engine.workspace import (
    clone_workspace,
    resolve_work_dir,
)
from opd.models.schemas import CreateProjectRequest, UpdateProjectRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Track running clone tasks by project id
_clone_tasks: dict[int, asyncio.Task] = {}
_clone_locks: dict[int, asyncio.Lock] = {}


def _launch_clone(project_id: int, repo_url: str) -> None:
    """Launch async git clone for a project."""
    # Get or create lock for this project
    lock = _clone_locks.setdefault(project_id, asyncio.Lock())

    async def _run_with_lock() -> None:
        async with lock:
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

    asyncio.create_task(_run_with_lock())


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
            for gc in result.scalars().all():
                if gc.config:
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
        workspace_dir=(req.workspace_dir or "").strip(),
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
async def get_project(project_id: int, db: AsyncSession = Depends(get_db),
                      orch: Orchestrator = Depends(get_orch)):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.rules),
            selectinload(Project.skills),
            selectinload(Project.stories),
            selectinload(Project.capability_configs).selectinload(
                ProjectCapabilityConfig.global_config
            ),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Only show capabilities that still exist in global config
    gc_result = await db.execute(
        select(GlobalCapabilityConfig).where(GlobalCapabilityConfig.enabled.is_(True))
    )
    global_keys = {
        f"{g.capability}/{g.provider}" for g in gc_result.scalars().all()
    }
    valid_caps = [
        c for c in project.capability_configs
        if f"{c.capability}/{c.provider_override or ''}" in global_keys
    ]
    return {
        "id": project.id,
        "name": project.name,
        "repo_url": project.repo_url,
        "description": project.description,
        "tech_stack": project.tech_stack,
        "architecture": project.architecture,
        "workspace_dir": project.workspace_dir,
        "workspace_path": str(resolve_work_dir(project)),
        "claude_md_ready": (resolve_work_dir(project) / "CLAUDE.md").is_file(),
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
        "capability_configs": [
            {
                "global_config_id": c.global_config_id,
                "capability": c.capability,
                "capability_label": _CAPABILITY_LABELS.get(c.capability, c.capability),
                "provider": c.provider_override or "",
                "provider_label": _PROVIDER_LABELS.get(c.provider_override or "", c.provider_override or ""),
                "label": c.global_config.label if c.global_config else None,
                "enabled": c.enabled,
            }
            for c in valid_caps
        ],
        "stories": [
            {"id": s.id, "title": s.title, "status": s.status.value}
            for s in project.stories
        ],
        "ai_running_count": orch.running_task_count(project_id),
    }


@router.put("/{project_id}")
async def update_project(
    project_id: int, req: UpdateProjectRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.name = req.name
    project.description = req.description or ""
    project.tech_stack = req.tech_stack or ""
    project.architecture = req.architecture or ""

    workspace_reclone = False

    # Handle repo_url change → trigger re-clone
    if req.repo_url is not None and req.repo_url != project.repo_url:
        project.repo_url = req.repo_url
        project.workspace_status = WorkspaceStatus.pending
        project.workspace_error = ""
        await db.flush()
        _launch_clone(project.id, req.repo_url)
        workspace_reclone = True

    # Handle workspace_dir change
    if req.workspace_dir is not None:
        project.workspace_dir = req.workspace_dir.strip()

    # Handle capabilities toggle
    if req.capabilities is not None:
        for toggle in req.capabilities:
            existing = None
            if toggle.global_config_id:
                cap_result = await db.execute(
                    select(ProjectCapabilityConfig).where(
                        ProjectCapabilityConfig.project_id == project_id,
                        ProjectCapabilityConfig.global_config_id == toggle.global_config_id,
                    )
                )
                existing = cap_result.scalar_one_or_none()
            if not existing:
                # Fallback: match by capability (for backwards compatibility)
                cap_result = await db.execute(
                    select(ProjectCapabilityConfig).where(
                        ProjectCapabilityConfig.project_id == project_id,
                        ProjectCapabilityConfig.capability == toggle.capability,
                        ProjectCapabilityConfig.global_config_id.is_(None),
                    )
                )
                existing = cap_result.scalar_one_or_none()
            if existing:
                existing.enabled = toggle.enabled
                existing.provider_override = toggle.provider or None
                existing.global_config_id = toggle.global_config_id
                existing.config_override = None
            else:
                db.add(ProjectCapabilityConfig(
                    project_id=project_id,
                    global_config_id=toggle.global_config_id,
                    capability=toggle.capability,
                    enabled=toggle.enabled,
                    provider_override=toggle.provider or None,
                    config_override=None,
                ))

    return {"id": project.id, "name": project.name, "workspace_reclone": workspace_reclone}


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
        provider_name = orch.capabilities.resolve_provider_name("scm", scm_cap.provider)
    else:
        # 2) Fallback: check GlobalCapabilityConfig table for first enabled SCM
        from opd.db.models import GlobalCapabilityConfig
        result = await db.execute(
            select(GlobalCapabilityConfig)
            .where(
                GlobalCapabilityConfig.capability == "scm",
                GlobalCapabilityConfig.enabled.is_(True),
            )
        )
        gc = result.scalars().first()
        if not gc:
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


@router.post("/{project_id}/sync-context")
async def sync_context(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    orch: Orchestrator = Depends(get_orch),
):
    """Sync workspace: pull latest if ready, clone if not."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.workspace_status == WorkspaceStatus.cloning:
        raise HTTPException(status_code=400, detail="工作区正在初始化中")

    task_key = f"project_sync_{project_id}"
    if orch.is_task_running(task_key):
        return {"status": "running", "message": "同步任务已在运行中"}

    _launch_sync_context(project_id, orch)
    return {"status": "started", "message": "同步任务已启动"}


@router.get("/{project_id}/sync-stream")
async def sync_stream(
    project_id: int,
    orch: Orchestrator = Depends(get_orch),
):
    """SSE endpoint for streaming sync-context progress."""
    task_key = f"project_sync_{project_id}"

    async def event_generator():
        queue = orch.subscribe(task_key)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            orch.unsubscribe(task_key, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _launch_sync_context(project_id: int, orch: Orchestrator) -> None:
    """Launch sync-context as a background task: pull or clone workspace."""
    task_key = f"project_sync_{project_id}"

    async def _run() -> None:
        await asyncio.sleep(0.3)
        session_factory = get_session_factory()
        done_event: dict | None = None
        try:
            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = result.scalar_one_or_none()
                    if not project:
                        done_event = {"type": "error", "content": "项目不存在"}
                        return

                    await orch.publish(task_key, {
                        "type": "system", "content": "正在拉取远端最新代码...",
                    })

                    from opd.engine.workspace import pull_main

                    ok = await pull_main(project)
                    if ok:
                        done_event = {
                            "type": "done",
                            "content": "代码同步完成",
                        }
                    else:
                        # pull failed (directory missing, not a git repo, etc.) — fallback to clone
                        await orch.publish(task_key, {
                            "type": "system", "content": "拉取失败，正在重新克隆工作区...",
                        })
                        token = await _resolve_scm_token(session_factory)
                        try:
                            await clone_workspace(project, project.repo_url, token=token)
                            project.workspace_status = WorkspaceStatus.ready
                            project.workspace_error = ""
                            done_event = {
                                "type": "done",
                                "content": "工作区重新克隆完成",
                            }
                        except Exception as clone_err:
                            logger.exception("Clone fallback failed for project %s", project_id)
                            project.workspace_status = WorkspaceStatus.error
                            project.workspace_error = str(clone_err)
                            done_event = {
                                "type": "error",
                                "content": f"克隆失败: {clone_err}",
                            }
                    logger.info("Sync context for project %s: %s", project_id, ok)
        except Exception as e:
            logger.exception("Sync context failed for project %s", project_id)
            done_event = {"type": "error", "content": str(e)}
        finally:
            orch.unregister_task(task_key)
            if done_event:
                await orch.publish(task_key, done_event)

    task = asyncio.create_task(_run())
    orch.register_task(task_key, task)


