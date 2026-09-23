"""Scheduled notification CRUD routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import ScheduledNotification, User
from app.db.session import get_db
from app.repositories.templates import NotificationRepository
from app.schemas import NotificationCreate, NotificationResponse
from app.services.agent.tools.notifications import ScheduleError, next_run_from_cron, parse_run_at

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    active_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await NotificationRepository(db).list_for_user(user.id, active_only)
    return [NotificationResponse.model_validate(n) for n in rows]


@router.post("", response_model=NotificationResponse, status_code=201)
async def create_notification(
    payload: NotificationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        next_run = (
            next_run_from_cron(payload.schedule_cron)
            if payload.schedule_cron
            else parse_run_at(payload.run_at.isoformat() if payload.run_at else None)
        )
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = NotificationRepository(db)
    entity = ScheduledNotification(
        user_id=user.id,
        message=payload.message,
        schedule_cron=payload.schedule_cron,
        run_at=payload.run_at,
        platform=payload.platform,
        target_chat_id=payload.target_chat_id,
        next_run=next_run,
        active=True,
    )
    await repo.add(entity)
    await db.commit()
    return NotificationResponse.model_validate(entity)


@router.post("/{notification_id}/toggle", response_model=NotificationResponse)
async def toggle_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationRepository(db)
    entity = await repo.get_owned(notification_id, user.id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan.")
    entity.active = not entity.active
    await db.commit()
    return NotificationResponse.model_validate(entity)


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationRepository(db)
    entity = await repo.get_owned(notification_id, user.id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan.")
    await repo.delete(entity)
    await db.commit()
    return None
