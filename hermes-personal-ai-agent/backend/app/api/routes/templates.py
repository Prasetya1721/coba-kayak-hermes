"""Command template CRUD routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import CommandTemplate, User
from app.db.session import get_db
from app.repositories.templates import TemplateRepository
from app.schemas import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    category: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    templates = await TemplateRepository(db).list_for_user(user.id, category)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TemplateRepository(db)
    entity = CommandTemplate(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        command_pattern=payload.command_pattern,
        category=payload.category,
        is_builtin=False,
    )
    await repo.add(entity)
    await db.commit()
    return TemplateResponse.model_validate(entity)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TemplateRepository(db)
    entity = await repo.get_owned(template_id, user.id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(entity, field, value)
    await db.commit()
    return TemplateResponse.model_validate(entity)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = TemplateRepository(db)
    entity = await repo.get_owned(template_id, user.id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan.")
    await repo.delete(entity)
    await db.commit()
    return None
