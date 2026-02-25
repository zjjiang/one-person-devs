"""Notification API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.deps import get_db
from opd.db.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return recent notifications, optionally filtered to unread."""
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": n.id,
            "type": n.type.value,
            "title": n.title,
            "message": n.message,
            "link": n.link,
            "read": n.read,
            "story_id": n.story_id,
            "project_id": n.project_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db)):
    """Return the number of unread notifications."""
    result = await db.execute(
        select(func.count(Notification.id)).where(Notification.read.is_(False))
    )
    return {"count": result.scalar_one()}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a single notification as read."""
    await db.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(read=True)
    )
    return {"ok": True}


@router.post("/read-all")
async def read_all(db: AsyncSession = Depends(get_db)):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(Notification.read.is_(False))
        .values(read=True)
    )
    return {"ok": True}
