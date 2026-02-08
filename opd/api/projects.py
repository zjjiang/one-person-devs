"""FastAPI router for Project CRUD and sub-resource management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_orchestrator, get_session
from opd.db.models import Project, Rule, Skill
from opd.engine.orchestrator import Orchestrator, ProjectNotFoundError
from opd.models.schemas import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    RuleCreate,
    RuleResponse,
    SkillCreate,
    SkillResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_or_404(
    db: AsyncSession, project_id: str
) -> Project:
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.rules),
            selectinload(Project.skills),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
) -> Project:
    project = await orch.create_project(db, body.model_dump())
    return project


@router.get(
    "",
    response_model=list[ProjectResponse],
    summary="List all projects",
)
async def list_projects(
    db: AsyncSession = Depends(get_session),
) -> list[Project]:
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get project detail with rules and skills",
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_session),
) -> Project:
    return await _get_project_or_404(db, project_id)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_session),
) -> Project:
    project = await _get_project_or_404(db, project_id)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    await db.flush()
    await db.refresh(project)
    return project


# ---------------------------------------------------------------------------
# Rules sub-resource
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a rule to a project",
)
async def add_rule(
    project_id: str,
    body: RuleCreate,
    db: AsyncSession = Depends(get_session),
) -> Rule:
    await _get_project_or_404(db, project_id)
    rule = Rule(
        project_id=project_id,
        category=body.category,
        content=body.content,
        enabled=body.enabled,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete(
    "/{project_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rule",
)
async def delete_rule(
    project_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.project_id == project_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found in project {project_id}",
        )
    await db.delete(rule)
    await db.flush()


# ---------------------------------------------------------------------------
# Skills sub-resource
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/skills",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill to a project",
)
async def add_skill(
    project_id: str,
    body: SkillCreate,
    db: AsyncSession = Depends(get_session),
) -> Skill:
    await _get_project_or_404(db, project_id)
    skill = Skill(
        project_id=project_id,
        name=body.name,
        description=body.description,
        command=body.command,
        trigger=body.trigger,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return skill


@router.delete(
    "/{project_id}/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a skill",
)
async def delete_skill(
    project_id: str,
    skill_id: str,
    db: AsyncSession = Depends(get_session),
) -> None:
    result = await db.execute(
        select(Skill).where(
            Skill.id == skill_id, Skill.project_id == project_id
        )
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill {skill_id} not found in project {project_id}",
        )
    await db.delete(skill)
    await db.flush()
