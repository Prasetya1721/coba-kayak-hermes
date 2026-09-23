"""Notification scheduler (APScheduler).

Polls `scheduled_notifications` for due rows and dispatches them through the
platform sender. Cron rows recompute `next_run`; one-shot rows deactivate after
firing. Runs in-process with FastAPI startup/shutdown.
"""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import ScheduledNotification
from app.db.session import SessionLocal
from app.services.agent.tools.notifications import next_run_from_cron
from app.services.gateways.sender import send_to_platform

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _dispatch_due() -> None:
    now = datetime.now(tz=timezone.utc)
    async with SessionLocal() as db:
        stmt = select(ScheduledNotification).where(
            ScheduledNotification.active.is_(True),
            ScheduledNotification.next_run.is_not(None),
            ScheduledNotification.next_run <= now,
        )
        due = list((await db.execute(stmt)).scalars().all())

        for item in due:
            if not item.target_chat_id:
                log.warning("notification_no_target", id=str(item.id))
                item.active = False
                continue

            ok = await send_to_platform(item.platform, item.target_chat_id, item.message)
            log.info(
                "notification_dispatched",
                id=str(item.id),
                platform=item.platform,
                ok=ok,
            )

            if item.schedule_cron:
                item.next_run = next_run_from_cron(item.schedule_cron, base=now)
            else:
                item.active = False

        await db.commit()


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("scheduler_disabled")
        return
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    _scheduler.add_job(
        _dispatch_due,
        trigger="interval",
        seconds=settings.scheduler_poll_seconds,
        id="dispatch_due_notifications",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("scheduler_started", interval=settings.scheduler_poll_seconds)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler_stopped")
