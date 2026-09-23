"""Chat routes: send a message, list sessions/history (decrypted server-side)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.repositories.chat import ChatLogRepository, ChatSessionRepository
from app.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
)
from app.services.agent.agent_service import AgentService, SessionNotFoundError
from app.services.credentials import resolve_user_credential

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Chat via dashboard (platform = telegram is used as the web pseudo-channel)."""

    async def _resolve(service_name: str) -> str:
        return await resolve_user_credential(db, user.id, service_name)

    agent = AgentService(db)
    try:
        session_id, result = await agent.handle_message(
            user_id=user.id,
            platform="telegram",
            platform_chat_id=f"web:{user.id}",
            message=payload.message,
            session_id=payload.session_id,
            credential_resolver=_resolve,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.") from exc
    return ChatResponse(
        session_id=session_id,
        reply=result.reply,
        scrubbed=result.scrubbed_input,
        detections=result.detections,
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    sessions = await ChatSessionRepository(db).list_by_user(user.id)
    return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_history(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = ChatSessionRepository(db)
    session = await sessions.get(session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")

    rows = await ChatLogRepository(db).list_by_session(session_id)
    messages = [
        ChatMessage(
            role=r["role"],
            content=r["content"],
            timestamp=r["timestamp"],  # type: ignore[arg-type]
        )
        for r in rows
    ]
    return ChatHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = ChatSessionRepository(db)
    session = await sessions.get_owned(session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")
    # Logs are deleted by the ON DELETE CASCADE on chat_logs.session_id.
    await sessions.delete(session)
    await db.commit()
    return None
