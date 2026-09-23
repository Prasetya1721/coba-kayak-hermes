"""Shared slowapi limiter and limit strings (single source of truth)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)

AUTH_LIMIT = "5/minute"
WEBHOOK_LIMIT = f"{settings.rate_limit_webhook_per_minute}/minute"
