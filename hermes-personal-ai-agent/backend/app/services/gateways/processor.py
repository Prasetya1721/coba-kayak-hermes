"""Webhook processing shared by Telegram and WhatsApp gateways.

Resolves the inbound platform chat to a user. Since HPA is single-user, the
owner is the first registered user; in a multi-user future this would consult a
`platform_links` table. Kept explicit and testable.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import User
from app.services.agent.agent_service import AgentService

log = get_logger(__name__)


async def resolve_owner(db: AsyncSession) -> User | None:
    """Return the primary (single) user for this self-hosted instance."""
    stmt = select(User).order_by(User.created_at.asc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def process_inbound(
    db: AsyncSession,
    *,
    platform: str,
    platform_chat_id: str,
    text: str,
) -> str:
    owner = await resolve_owner(db)
    if owner is None:
        log.warning("inbound_no_owner", platform=platform)
        return "Belum ada pengguna terdaftar. Silakan daftar di dashboard terlebih dahulu."

    agent = AgentService(db)
    _, result = await agent.handle_message(
        user_id=owner.id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        message=text,
    )
    return result.reply
