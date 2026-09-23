"""Onboarding status route used by the frontend wizard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.repositories.templates import NotificationRepository, TemplateRepository
from app.repositories.users import CredentialRepository
from app.schemas import OnboardingStatus
from app.services.agent.llm import llm_is_configured

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    creds = await CredentialRepository(db).list(limit=100)
    owned_creds = {c.service_name for c in creds if c.user_id == user.id}
    templates = await TemplateRepository(db).list_for_user(user.id)
    notifications = await NotificationRepository(db).list_for_user(user.id)

    steps = {
        "account_created": True,
        "consent_given": user.consent_given,
        "llm_configured": llm_is_configured() or "llm" in owned_creds,
        "telegram_connected": bool(settings.telegram_bot_token),
        "whatsapp_connected": settings.whatsapp_provider != "none",
        "template_selected": len(templates) > 0,
        "notification_created": len(notifications) > 0,
    }
    next_step = next((k for k, v in steps.items() if not v), None)
    return OnboardingStatus(completed=next_step is None, steps=steps, next_step=next_step)
