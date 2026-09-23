"""Notification scheduling tool helpers (used by the AI agent and APScheduler).

The agent-facing tool returns a JSON-serialisable descriptor; the service layer
persists it. Cron expressions are validated with `croniter`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter

from app.core.config import settings


class ScheduleError(ValueError):
    pass


def validate_cron(expr: str) -> str:
    expr = (expr or "").strip()
    if not croniter.is_valid(expr):
        raise ScheduleError(f"Ekspresi cron tidak valid: {expr}")
    return expr


def next_run_from_cron(expr: str, base: datetime | None = None) -> datetime:
    validate_cron(expr)
    base = base or datetime.now(tz=timezone.utc)
    nxt = croniter(expr, base).get_next(datetime)
    return nxt if nxt.tzinfo else nxt.replace(tzinfo=timezone.utc)


def parse_run_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScheduleError(f"Format waktu tidak valid: {value}") from exc
    tz_name = settings.scheduler_timezone
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.astimezone(timezone.utc)
