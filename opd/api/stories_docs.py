"""Story document management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
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


@docs_router.get("/stories/{story_id}/docs/{filename}/download")
async def download_story_doc(story_id: int, filename: str, db: AsyncSession = Depends(get_db)):
    """Download a story document as a .md file."""
    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    content = read_doc(story.project, story, filename)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    name_part = filename.removesuffix(".md")
    download_name = f"story-{story_id}-{name_part}.md"
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@docs_router.post("/stories/{story_id}/docs/upload")
async def upload_story_doc(story_id: int, file: UploadFile, db: AsyncSession = Depends(get_db)):
    """Upload a .md file to replace a story document."""
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are allowed")
    if file.filename not in DOC_FILENAME_MAP:
        allowed = ", ".join(sorted(DOC_FILENAME_MAP.keys()))
        raise HTTPException(status_code=400, detail=f"Unknown document. Allowed: {allowed}")

    result = await db.execute(
        select(Story).where(Story.id == story_id).options(selectinload(Story.project))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    rel_path = write_doc(story.project, story, file.filename, content)
    db_field = DOC_FILENAME_MAP.get(file.filename)
    if db_field:
        setattr(story, db_field, rel_path)
    return {"filename": file.filename, "path": rel_path}
