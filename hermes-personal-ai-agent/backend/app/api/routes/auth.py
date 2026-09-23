"""Auth routes: register, login, refresh, me, profile."""

# NOTE: no `from __future__ import annotations` here. The @limiter.limit
# decorator wraps these endpoints; with PEP 563 the annotations become strings
# that FastAPI cannot resolve in the wrapper's namespace (would break param
# injection the same way it did for webhooks).

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import AUTH_LIMIT, limiter
from app.db.models import User
from app.db.session import get_db
from app.schemas import (
    LoginRequest,
    ProfileResponse,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit(AUTH_LIMIT)
async def register(
    request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)
):
    return await AuthService(db).register(payload)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
async def login(
    request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)
):
    return await AuthService(db).login(payload)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(AUTH_LIMIT)
async def refresh(
    request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)
):
    return await AuthService(db).refresh(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    profile = await AuthService(db).profiles.get_by_user(user.id)
    if profile is None:
        return ProfileResponse(user_id=user.id)
    return ProfileResponse.model_validate(profile)


@router.put("/profile", response_model=ProfileUpdate)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await AuthService(db).update_profile(user.id, payload)
