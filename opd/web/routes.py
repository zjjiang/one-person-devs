"""Web UI routes for OPD.

Renders Jinja2 templates with data fetched directly from the database.
Forms submit to the JSON API endpoints via JavaScript fetch().
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fastapi.templating import Jinja2Templates

from opd.api.deps import get_session
from opd.db.models import (
    AIMessage,
    Project,
    Round,
    Story,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["web"])


def _extract_json_str(text: str) -> str:
    """Strip markdown code fences and find the first JSON object/array."""
    fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced[0].strip()
    for sc, ec in [('{', '}'), ('[', ']')]:
        start = text.find(sc)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == sc:
                depth += 1
            elif text[i] == ec:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return text


def _parse_plan_steps(raw: str) -> list[dict]:
    """Parse plan JSON (possibly nested/malformed) into a list of step dicts."""
    steps: list[dict] = []
    # Try direct parse first, then fall back to extraction
    data = None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        cleaned = _extract_json_str(raw)
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return steps

    if data is None:
        return steps

    if isinstance(data, dict) and "steps" in data:
        for step in data["steps"]:
            if not isinstance(step, dict):
                continue
            desc = step.get("description", "")
            files = step.get("files", [])
            # Check if description itself contains nested JSON with steps
            if "steps" in desc and ("{" in desc or "```" in desc):
                inner_json = _extract_json_str(desc)
                try:
                    inner = json.loads(inner_json)
                    if isinstance(inner, dict) and "steps" in inner:
                        return _parse_plan_steps(json.dumps(inner))
                except (json.JSONDecodeError, ValueError):
                    pass
            steps.append({"description": desc, "files": files})
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                steps.append({
                    "description": item.get("description", str(item)),
                    "files": item.get("files", []),
                })
    return steps


# ---------------------------------------------------------------------------
# Dashboard / Project list
# ---------------------------------------------------------------------------

@router.get("/", name="index")
async def index(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Dashboard showing all projects."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    projects = list(result.scalars().all())

    story_counts: dict[str, int] = {}
    if projects:
        count_result = await db.execute(
            select(Story.project_id, func.count(Story.id))
            .group_by(Story.project_id)
        )
        story_counts = dict(count_result.all())

    return templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "story_counts": story_counts,
    })


# ---------------------------------------------------------------------------
# Create project form  (MUST be before /projects/{project_id})
# ---------------------------------------------------------------------------

@router.get("/projects/new", name="project_form")
async def project_form(request: Request):
    """Form to create a new project."""
    return templates.TemplateResponse("project_form.html", {
        "request": request,
    })


# ---------------------------------------------------------------------------
# Project detail
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}", name="project_detail")
async def project_detail(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Project detail page with rules, skills, and stories."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.rules),
            selectinload(Project.skills),
            selectinload(Project.stories),
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    stories = sorted(project.stories, key=lambda s: s.created_at, reverse=True)

    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project,
        "stories": stories,
    })


# ---------------------------------------------------------------------------
# Create story form
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/stories/new", name="story_form")
async def story_form(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Form to create a new story for a project."""
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    return templates.TemplateResponse("story_form.html", {
        "request": request,
        "project": project,
    })


# ---------------------------------------------------------------------------
# Story detail
# ---------------------------------------------------------------------------

@router.get("/stories/{story_id}", name="story_detail")
async def story_detail(
    story_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Story detail page with rounds, clarifications, and AI logs."""
    result = await db.execute(
        select(Story)
        .options(
            selectinload(Story.rounds)
            .selectinload(Round.clarifications),
        )
        .where(Story.id == story_id)
    )
    story = result.scalar_one_or_none()
    if story is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story {story_id} not found",
        )

    active_round = None
    if story.rounds:
        active_round = max(story.rounds, key=lambda r: r.round_number)

    ai_messages: list[AIMessage] = []
    plan_content: str | None = None
    plan_steps: list[dict] = []
    coding_msg_count: int = 0
    latest_activity: str | None = None
    if active_round:
        msg_result = await db.execute(
            select(AIMessage)
            .where(AIMessage.round_id == active_round.id)
            .order_by(AIMessage.created_at.asc())
        )
        ai_messages = list(msg_result.scalars().all())
        # Extract the latest plan content for display
        for msg in reversed(ai_messages):
            if "[Implementation Plan]" in msg.content or "[Revised Plan]" in msg.content:
                raw = msg.content.split("\n", 1)[1] if "\n" in msg.content else msg.content
                plan_content = raw
                plan_steps = _parse_plan_steps(raw)
                break

        # Count coding-phase messages and find latest activity
        for msg in ai_messages:
            if msg.role.value == "assistant" and "[Implementation Plan]" not in msg.content and "[Revised Plan]" not in msg.content and "[Plan Feedback]" not in msg.content:
                coding_msg_count += 1
            if msg.role.value == "tool":
                coding_msg_count += 1
        # Latest non-plan assistant message
        for msg in reversed(ai_messages):
            c = msg.content
            if "[Implementation Plan]" in c or "[Revised Plan]" in c or "[Plan Feedback]" in c:
                continue
            if msg.role.value == "assistant" and len(c) < 300:
                latest_activity = c[:150]
                break
            if msg.role.value == "tool":
                try:
                    import json as _json
                    tool_data = _json.loads(c)
                    tool_name = tool_data.get("tool", "")
                    if tool_name:
                        latest_activity = f"正在使用工具: {tool_name}"
                        break
                except (ValueError, TypeError):
                    pass

    return templates.TemplateResponse("story_detail.html", {
        "request": request,
        "story": story,
        "active_round": active_round,
        "ai_messages": ai_messages,
        "plan_content": plan_content,
        "plan_steps": plan_steps,
        "coding_msg_count": coding_msg_count,
        "latest_activity": latest_activity,
    })
