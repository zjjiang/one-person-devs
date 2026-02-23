"""Story document management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opd.api.deps import get_db
from opd.db.models import Story
from opd.engine.workspace import DOC_FILENAME_MAP, list_docs, read_doc, write_doc
from opd.models.schemas import UpdateDocRequest

docs_router = APIRouter(prefix="/api", tags=["stories"])


@docs_router.get("/stories/{story_id}/docs")
async def list_story_docs(story_id: int, db: AsyncSession = Depends(get_db)):
    """List document files for a story."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    files = list_docs(story.project, story)
    return {"files": files}


@docs_router.get("/stories/{story_id}/docs/{filename}")
async def get_story_doc(story_id: int, filename: str, db: AsyncSession = Depends(get_db)):
    """Read a story document file."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    content = read_doc(story.project, story, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"filename": filename, "content": content}


@docs_router.put("/stories/{story_id}/docs/{filename}")
async def save_story_doc(
    story_id: int, filename: str, req: UpdateDocRequest,
    db: AsyncSession = Depends(get_db),
):
    """Write a story document file, store path in DB."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    rel_path = write_doc(story.project, story, filename, req.content)
    # Update the corresponding DB field if it maps to a known doc
    db_field = DOC_FILENAME_MAP.get(filename)
    if db_field:
        setattr(story, db_field, rel_path)
    return {"filename": filename, "path": rel_path}
