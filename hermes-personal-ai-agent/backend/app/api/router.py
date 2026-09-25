"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    auth,
    chat,
    credentials,
    memories,
    models,
    notifications,
    onboarding,
    privacy,
    templates,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(templates.router)
api_router.include_router(notifications.router)
api_router.include_router(credentials.router)
api_router.include_router(memories.router)
api_router.include_router(models.router)
api_router.include_router(privacy.router)
api_router.include_router(onboarding.router)
api_router.include_router(webhooks.router)
