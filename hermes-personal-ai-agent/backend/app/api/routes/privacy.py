"""Privacy routes (UU PDP): data export and right-to-be-forgotten.

All decryption happens server-side; the export is returned directly to the
authenticated owner and never persisted elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.crypto import decrypt
from app.db.models import User
from app.db.session import get_db
from app.repositories.chat import ChatLogRepository, ChatSessionRepository
from app.repositories.templates import NotificationRepository, TemplateRepository
from app.repositories.users import CredentialRepository, ProfileRepository
from app.schemas import (
    ChatMessage,
    ChatSessionResponse,
    DataExportResponse,
    DeleteDataResponse,
    NotificationResponse,
    ProfileResponse,
    TemplateResponse,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/export", response_model=DataExportResponse)
async def export_data(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Export everything held about the user in a portable JSON document."""
    profile = await ProfileRepository(db).get_by_user(user.id)
    all_templates = await TemplateRepository(db).list_for_user(user.id)
    # Export only the user's own templates; built-ins can be re-seeded anytime.
    templates = [t for t in all_templates if not t.is_builtin]
    notifications = await NotificationRepository(db).list_for_user(user.id)
    sessions = await ChatSessionRepository(db).list_by_user(user.id)

    logs = ChatLogRepository(db)
    chat_messages: dict[str, list[ChatMessage]] = {}
    for s in sessions:
        rows = await logs.list_by_session(s.id)
        chat_messages[str(s.id)] = [
            ChatMessage(role=r["role"], content=r["content"]) for r in rows
        ]

    return DataExportResponse(
        exported_at=datetime.now(tz=timezone.utc),
        profile=ProfileResponse.model_validate(profile) if profile else None,
        templates=[TemplateResponse.model_validate(t) for t in templates],
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        sessions=[ChatSessionResponse.model_validate(s) for s in sessions],
        chat_messages=chat_messages,
    )


@router.delete("/data", response_model=DeleteDataResponse)
async def delete_all_data(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Delete all chat history, templates, notifications, and credentials.

    The account itself is retained so the user can keep using the agent; use
    `DELETE /privacy/account` to remove everything.
    """
    await ChatSessionRepository(db).delete_by_user(user.id)  # cascades to logs
    await NotificationRepository(db).delete_by_user(user.id)
    await TemplateRepository(db).delete_by_user(user.id)
    await CredentialRepository(db).delete_by_user(user.id)
    await MemoryService(db).delete_by_user(user.id)
    await db.commit()
    return DeleteDataResponse(
        deleted=True,
        detail="Semua riwayat chat, template, notifikasi, kredensial, dan ingatan telah dihapus.",
    )


@router.delete("/account", status_code=204)
async def delete_account(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Hard-delete the account and every related row (right to be forgotten)."""
    if not user.consent_given:
        # still allow deletion; consent flag is informational
        pass
    await db.delete(user)
    await db.commit()
    return None


__all__ = ["router", "decrypt"]  # re-export for tests
