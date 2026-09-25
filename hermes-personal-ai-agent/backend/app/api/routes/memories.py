"""Permanent memory CRUD routes (user-owned facts, encrypted at rest)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas import MemoryCreate, MemoryResponse
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MemoryService(db).list(user.id)


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        saved = await MemoryService(db).save(
            user.id, payload.key, payload.value, scope=payload.scope
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return saved


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await MemoryService(db).delete(user.id, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ingatan tidak ditemukan.")
    await db.commit()
    return None
