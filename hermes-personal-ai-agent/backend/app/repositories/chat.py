"""Chat session & encrypted chat-log repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from app.core.crypto import decrypt, encrypt
from app.db.models import ChatLog, ChatSession
from app.repositories.base import BaseRepository


class ChatSessionRepository(BaseRepository[ChatSession]):
    model = ChatSession

    async def get_owned(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession | None:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        user_id: uuid.UUID,
        platform: str,
        platform_chat_id: str,
    ) -> ChatSession:
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.platform == platform,
                ChatSession.platform_chat_id == platform_chat_id,
                ChatSession.user_id == user_id,
            )
            .order_by(ChatSession.created_at.desc())
            .limit(1)
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            if existing.user_id is None:
                existing.user_id = user_id
                await self.session.flush()
            return existing
        session = ChatSession(
            user_id=user_id,
            platform=platform,
            platform_chat_id=platform_chat_id,
        )
        return await self.add(session)

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 100
    ) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(ChatSession).where(ChatSession.user_id == user_id)
        )
        return result.rowcount or 0


class ChatLogRepository(BaseRepository[ChatLog]):
    model = ChatLog

    async def append(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        meta: str | None = None,
    ) -> ChatLog:
        log = ChatLog(
            session_id=session_id,
            role=role,
            content_encrypted=encrypt(content),
            meta=meta,
        )
        return await self.add(log)

    async def recent(
        self, session_id: uuid.UUID, limit: int = 10
    ) -> list[dict[str, str]]:
        """Return the last `limit` messages in chronological order (decrypted)."""
        stmt = (
            select(ChatLog)
            .where(ChatLog.session_id == session_id)
            .order_by(ChatLog.timestamp.desc())
            .limit(limit)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.reverse()
        return [
            {
                "role": row.role,
                "content": self._safe_decrypt(row.content_encrypted),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "meta": row.meta,
            }
            for row in rows
        ]

    async def list_by_session(
        self, session_id: uuid.UUID, limit: int = 200, offset: int = 0
    ) -> list[dict[str, str]]:
        stmt = (
            select(ChatLog)
            .where(ChatLog.session_id == session_id)
            .order_by(ChatLog.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [
            {
                "role": row.role,
                "content": self._safe_decrypt(row.content_encrypted),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]

    async def count_by_session(self, session_id: uuid.UUID) -> int:
        from sqlalchemy import func

        stmt = select(func.count(ChatLog.id)).where(ChatLog.session_id == session_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def purge_session(self, session_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(ChatLog).where(ChatLog.session_id == session_id)
        )
        return result.rowcount or 0

    @staticmethod
    def _safe_decrypt(blob: bytes) -> str:
        try:
            return decrypt(blob)
        except Exception:  # noqa: BLE001
            return "[unable to decrypt]"
