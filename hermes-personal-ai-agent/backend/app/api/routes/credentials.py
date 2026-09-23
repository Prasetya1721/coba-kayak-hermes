"""Encrypted credential storage routes (Vault/KMS-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.crypto import EncryptionError, encrypt
from app.db.models import User
from app.db.session import get_db
from app.repositories.users import CredentialRepository
from app.schemas import CredentialCreate, CredentialResponse

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """List stored services (metadata only — tokens are never returned)."""
    repo = CredentialRepository(db)
    rows = await repo.list(limit=100)
    owned = [r for r in rows if r.user_id == user.id]
    return [CredentialResponse.model_validate(c) for c in owned]


@router.post("", response_model=CredentialResponse, status_code=201)
async def store_credential(
    payload: CredentialCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        blob = encrypt(payload.token)
    except EncryptionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    repo = CredentialRepository(db)
    entity = await repo.upsert(user.id, payload.service_name, blob)
    await db.commit()
    return CredentialResponse.model_validate(entity)


@router.delete("/{service_name}", status_code=204)
async def delete_credential(
    service_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = CredentialRepository(db)
    entity = await repo.get_service_token(user.id, service_name)
    if entity is None:
        raise HTTPException(status_code=404, detail="Kredensial tidak ditemukan.")
    await repo.delete(entity)
    await db.commit()
    return None
