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
from opd.db.models import Project, ProjectCapabilityConfig, WorkspaceStatus
from opd.db.session import get_session_factory
from opd.engine.orchestrator import Orchestrator
from opd.engine.workspace import (
    clone_workspace,
    commit_and_push_file,
    get_latest_merge_diff,
    resolve_work_dir,
    scan_workspace,
)
from opd.models.schemas import CreateProjectRequest, UpdateProjectRequest

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
        "capability_configs": [
            {"capability": c.capability, "provider": c.provider_override or "", "enabled": c.enabled}
            for c in project.capability_configs
        ],
        "stories": [
            {"id": s.id, "title": s.title, "status": s.status.value}
            for s in project.stories
        ],
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
        project.workspace_dir = req.workspace_dir

    # Handle capabilities toggle (enabled only, no provider/config override)
    if req.capabilities is not None:
        for toggle in req.capabilities:
            cap_result = await db.execute(
                select(ProjectCapabilityConfig).where(
                    ProjectCapabilityConfig.project_id == project_id,
                    ProjectCapabilityConfig.capability == toggle.capability,
                )
            )
            existing = cap_result.scalar_one_or_none()
            if existing:
                existing.enabled = toggle.enabled
                existing.provider_override = toggle.provider or None
                existing.config_override = None
            else:
                db.add(ProjectCapabilityConfig(
                    project_id=project_id,
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
    """Launch background task to scan workspace, call AI to generate CLAUDE.md, commit and push."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.workspace_status != WorkspaceStatus.ready:
        raise HTTPException(status_code=400, detail="工作区未就绪")

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
    """Launch sync-context as a background task with SSE streaming."""
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
                        "type": "system", "content": "正在扫描项目工作区...",
                    })

                    source_ctx = scan_workspace(project, max_depth=4, max_chars=12000)
                    if not source_ctx:
                        done_event = {"type": "error", "content": "工作区扫描为空"}
                        return

                    work_dir = resolve_work_dir(project)
                    existing_claude_md = ""
                    claude_md_path = work_dir / "CLAUDE.md"
                    if claude_md_path.is_file():
                        existing_claude_md = claude_md_path.read_text(encoding="utf-8")

                    await orch.publish(task_key, {
                        "type": "system", "content": "工作区扫描完成，正在调用 AI 生成 CLAUDE.md...",
                    })

                    from opd.api.stories_tasks import _build_project_registry
                    registry = await _build_project_registry(db, orch, project_id)
                    ai_cap = registry.get("ai")
                    if not ai_cap:
                        done_event = {"type": "error", "content": "AI 能力未配置"}
                        return

                    claude_md = await _ai_generate_claude_md(
                        ai_cap, project, source_ctx, existing_claude_md,
                        publish=lambda msg: orch.publish(task_key, msg),
                    )

                    await orch.publish(task_key, {
                        "type": "system", "content": "AI 生成完成，正在提交并推送到远端...",
                    })

                    pushed = await commit_and_push_file(
                        project, "CLAUDE.md", "chore: update CLAUDE.md project context",
                        content=claude_md,
                    )
                    if pushed:
                        done_event = {
                            "type": "done",
                            "content": "CLAUDE.md 已生成并推送到远端",
                        }
                    else:
                        (work_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
                        done_event = {
                            "type": "done",
                            "content": "CLAUDE.md 已生成（推送失败，仅本地）",
                        }
                    logger.info("Generated CLAUDE.md for project %s", project_id)
        except Exception as e:
            logger.exception("Sync context failed for project %s", project_id)
            done_event = {"type": "error", "content": str(e)}
        finally:
            orch.unregister_task(task_key)
            if done_event:
                await orch.publish(task_key, done_event)

    task = asyncio.create_task(_run())
    orch.register_task(task_key, task)


async def _ai_generate_claude_md(
    ai_cap, project: Project, source_context: str, existing: str,
    *, publish=None,
) -> str:
    """Call AI to generate a comprehensive CLAUDE.md."""
    system_prompt = (
        "你是一个资深工程师。根据项目的源码结构和关键文件内容，"
        "生成一份 CLAUDE.md 文件，供 AI 编码助手理解项目上下文。\n\n"
        "CLAUDE.md 应包含：\n"
        "- 项目概述（一句话描述）\n"
        "- 技术栈\n"
        "- 项目架构（请求流、核心模块、数据流）\n"
        "- 常用命令（启动、测试、构建、lint）\n"
        "- 关键目录和文件说明\n"
        "- 编码规范和注意事项\n\n"
        "直接输出 Markdown 内容，不要包含 ```markdown 代码块包裹。"
    )

    parts = []
    if project.description:
        parts.append(f"## 项目描述\n{project.description}")
    if project.tech_stack:
        parts.append(f"## 技术栈\n{project.tech_stack}")
    if project.architecture:
        parts.append(f"## 架构\n{project.architecture}")
    parts.append(source_context)
    if existing:
        parts.append(f"## 现有 CLAUDE.md（供参考，可保留有价值的内容）\n{existing}")

    user_prompt = "\n\n".join(parts)

    collected: list[str] = []
    async for msg in ai_cap.provider.plan(system_prompt, user_prompt):
        if msg.get("type") == "assistant" and msg.get("content"):
            collected.append(msg["content"])
            if publish:
                await publish({"type": "assistant", "content": msg["content"]})

    return "\n".join(collected).strip() if collected else _fallback_claude_md(project, source_context)


def _fallback_claude_md(project: Project, source_context: str) -> str:
    """Fallback: generate CLAUDE.md without AI from project metadata."""
    sections = [f"# {project.name}\n"]
    if project.description:
        sections.append(f"## 项目描述\n{project.description}\n")
    if project.tech_stack:
        sections.append(f"## 技术栈\n{project.tech_stack}\n")
    if project.architecture:
        sections.append(f"## 架构\n{project.architecture}\n")
    sections.append(source_context)
    return "\n".join(sections)


def launch_incremental_claude_md_update(project_id: int, orch: Orchestrator) -> None:
    """Launch background task to incrementally update CLAUDE.md after merge.

    Non-blocking: fires and forgets. Failures are logged but do not propagate.
    """
    task_key = f"project_claude_md_{project_id}"
    if orch.is_task_running(task_key):
        return

    async def _run() -> None:
        await asyncio.sleep(0.5)  # Let merge DB commit settle
        session_factory = get_session_factory()
        try:
            async with session_factory() as db:
                async with db.begin():
                    result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = result.scalar_one_or_none()
                    if not project:
                        return

                    diff_summary = await get_latest_merge_diff(project)
                    if not diff_summary:
                        logger.info("No merge diff found for project %s, skipping", project_id)
                        return

                    work_dir = resolve_work_dir(project)
                    claude_md_path = work_dir / "CLAUDE.md"
                    if not claude_md_path.is_file():
                        logger.info("No CLAUDE.md for project %s, skipping incremental", project_id)
                        return
                    existing = claude_md_path.read_text(encoding="utf-8")

                    from opd.api.stories_tasks import _build_project_registry
                    registry = await _build_project_registry(db, orch, project_id)
                    ai_cap = registry.get("ai")
                    if not ai_cap:
                        return

                    updated = await _ai_incremental_update_claude_md(
                        ai_cap, diff_summary, existing,
                    )
                    if updated and updated != existing:
                        await commit_and_push_file(
                            project, "CLAUDE.md",
                            "chore: incremental update CLAUDE.md after merge",
                            content=updated,
                        )
                        logger.info("Incremental CLAUDE.md update for project %s", project_id)
        except Exception:
            logger.exception("Incremental CLAUDE.md update failed for project %s", project_id)
        finally:
            orch.unregister_task(task_key)

    task = asyncio.create_task(_run())
    orch.register_task(task_key, task)


async def _ai_incremental_update_claude_md(
    ai_cap, diff_summary: str, existing: str,
) -> str:
    """Call AI to incrementally update CLAUDE.md based on merge diff."""
    system_prompt = (
        "你是一个资深工程师。根据最近一次合并的代码变更，增量更新项目的 CLAUDE.md 文件。\n\n"
        "规则：\n"
        "- 只修改受变更影响的部分\n"
        "- 保留现有内容中仍然准确的部分\n"
        "- 如果变更引入了新模块/API/配置，添加相应说明\n"
        "- 如果变更删除或重命名了内容，更新对应描述\n"
        "- 直接输出完整的 CLAUDE.md 内容，不要用 ```markdown 包裹"
    )
    user_prompt = f"## 现有 CLAUDE.md\n{existing}\n\n## 最近合并的变更\n{diff_summary}"

    collected: list[str] = []
    async for msg in ai_cap.provider.plan(system_prompt, user_prompt):
        if msg.get("type") == "assistant" and msg.get("content"):
            collected.append(msg["content"])

    return "\n".join(collected).strip() if collected else existing
