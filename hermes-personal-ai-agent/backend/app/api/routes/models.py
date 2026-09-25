"""LLM model routing: view the failover chain and switch models manually."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User
from app.schemas import ModelInfo, ModelListResponse, ModelSwitchRequest
from app.services.agent import llm

router = APIRouter(prefix="/models", tags=["models"])


def _to_models() -> list[ModelInfo]:
    return [ModelInfo(**m) for m in llm.available_models()]


@router.get("", response_model=ModelListResponse)
async def list_models(user: User = Depends(get_current_user)):
    """Configured failover chain with the current active model."""
    return ModelListResponse(
        active=llm.active_model(),
        provider=settings.llm_provider,
        models=_to_models(),
    )


@router.post("/switch", response_model=ModelListResponse)
async def switch_model(
    payload: ModelSwitchRequest,
    user: User = Depends(get_current_user),
):
    """Manually pick the active model. It moves to the front of the chain."""
    model = (payload.model or "").strip()
    chain = settings.llm_model_chain
    if model not in chain:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Model '{model}' tidak ada di chain. "
                f"Pilihan: {', '.join(chain) or '(kosong)'}"
            ),
        )
    llm.set_active_model(model)
    return ModelListResponse(
        active=llm.active_model(),
        provider=settings.llm_provider,
        models=_to_models(),
    )


@router.post("/reset", response_model=ModelListResponse)
async def reset_models(user: User = Depends(get_current_user)):
    """Clear all cooldowns and go back to the configured default model."""
    llm.clear_cooldown()
    llm.set_active_model(settings.openai_model)
    return ModelListResponse(
        active=llm.active_model(),
        provider=settings.llm_provider,
        models=_to_models(),
    )
