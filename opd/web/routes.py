"""Web UI routes (Jinja2 templates)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db
from opd.db.models import Project, Round, RoundStatus, Story

templates = Jinja2Templates(directory="opd/web/templates")
router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).options(selectinload(Project.stories))
    )
    projects = result.scalars().all()
    return templates.TemplateResponse("index.html", {
        "request": request, "projects": projects,
    })


@router.get("/projects/new", response_class=HTMLResponse)
async def project_form(request: Request):
    return templates.TemplateResponse("project_form.html", {
        "request": request, "project": None,
    })


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, request: Request,
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.stories),
            selectinload(Project.rules),
            selectinload(Project.skills),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return HTMLResponse("Project not found", status_code=404)
    return templates.TemplateResponse("project_detail.html", {
        "request": request, "project": project,
    })


@router.get("/projects/{project_id}/stories/new", response_class=HTMLResponse)
async def story_form(project_id: int, request: Request,
                     db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    return templates.TemplateResponse("story_form.html", {
        "request": request, "project": project,
    })


@router.get("/stories/{story_id}", response_class=HTMLResponse)
async def story_detail(story_id: int, request: Request,
                       db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Story)
        .where(Story.id == story_id)
        .options(
            selectinload(Story.project),
            selectinload(Story.tasks),
            selectinload(Story.rounds).selectinload(Round.pull_requests),
            selectinload(Story.clarifications),
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        return HTMLResponse("Story not found", status_code=404)
    active_round = next(
        (r for r in story.rounds if r.status == RoundStatus.active), None
    )
    return templates.TemplateResponse("story_detail.html", {
        "request": request, "story": story, "active_round": active_round,
    })
