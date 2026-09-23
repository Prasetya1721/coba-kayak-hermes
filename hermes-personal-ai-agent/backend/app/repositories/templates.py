"""Template and notification repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select

from app.db.models import CommandTemplate, ScheduledNotification
from app.repositories.base import BaseRepository


class TemplateRepository(BaseRepository[CommandTemplate]):
    model = CommandTemplate

    async def list_for_user(
        self, user_id: uuid.UUID, category: str | None = None
    ) -> list[CommandTemplate]:
        """Return the user's templates plus all built-in templates."""
        conditions = [CommandTemplate.is_builtin.is_(True), CommandTemplate.user_id == user_id]
        stmt = select(CommandTemplate).where(or_(*conditions))
        if category:
            stmt = stmt.where(CommandTemplate.category == category)
        stmt = stmt.order_by(CommandTemplate.is_builtin.desc(), CommandTemplate.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_builtin(self) -> list[CommandTemplate]:
        stmt = select(CommandTemplate).where(CommandTemplate.is_builtin.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_owned(
        self, template_id: uuid.UUID, user_id: uuid.UUID
    ) -> CommandTemplate | None:
        stmt = select(CommandTemplate).where(
            CommandTemplate.id == template_id,
            CommandTemplate.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class NotificationRepository(BaseRepository[ScheduledNotification]):
    model = ScheduledNotification

    async def list_for_user(
        self, user_id: uuid.UUID, active_only: bool = False
    ) -> list[ScheduledNotification]:
        stmt = select(ScheduledNotification).where(
            ScheduledNotification.user_id == user_id
        )
        if active_only:
            stmt = stmt.where(ScheduledNotification.active.is_(True))
        stmt = stmt.order_by(ScheduledNotification.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_owned(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> ScheduledNotification | None:
        stmt = select(ScheduledNotification).where(
            ScheduledNotification.id == notification_id,
            ScheduledNotification.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_due(self, now) -> list[ScheduledNotification]:
        stmt = select(ScheduledNotification).where(
            ScheduledNotification.active.is_(True),
            ScheduledNotification.next_run.is_not(None),
            ScheduledNotification.next_run <= now,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_one_shot_pending(self) -> list[ScheduledNotification]:
        stmt = select(ScheduledNotification).where(
            ScheduledNotification.active.is_(True),
            ScheduledNotification.run_at.is_not(None),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(ScheduledNotification).where(
                ScheduledNotification.user_id == user_id
            )
        )
        return result.rowcount or 0
