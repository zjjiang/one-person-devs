"""Project management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db
from opd.db.models import Project
from opd.models.schemas import CreateProjectRequest

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
async def create_project(req: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=req.name,
        repo_url=req.repo_url,
        description=req.description or "",
        tech_stack=req.tech_stack or "",
        architecture=req.architecture or "",
    )
    db.add(project)
    await db.flush()
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
        return {"error": "Project not found"}, 404
    return {
        "id": project.id,
        "name": project.name,
        "repo_url": project.repo_url,
        "description": project.description,
        "tech_stack": project.tech_stack,
        "architecture": project.architecture,
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
        return {"error": "Project not found"}, 404
    project.name = req.name
    project.repo_url = req.repo_url
    project.description = req.description or ""
    project.tech_stack = req.tech_stack or ""
    project.architecture = req.architecture or ""
    return {"id": project.id, "name": project.name}
