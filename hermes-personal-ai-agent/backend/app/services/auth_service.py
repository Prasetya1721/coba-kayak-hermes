"""Authentication service: register, login, refresh, current-user resolution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.repositories.users import ProfileRepository, UserRepository
from app.schemas import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.profiles = ProfileRepository(session)

    async def register(self, payload: RegisterRequest) -> UserResponse:
        if not payload.consent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Persetujuan (consent) UU PDP wajib diberikan untuk mendaftar.",
            )
        if await self.users.get_by_username(payload.username):
            raise HTTPException(status_code=409, detail="Username sudah digunakan.")
        if await self.users.get_by_email(payload.email):
            raise HTTPException(status_code=409, detail="Email sudah terdaftar.")

        user = await self.users.create(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            consent=True,
        )
        await self.profiles.upsert(
            user.id,
            display_name=payload.display_name or payload.username,
            phone_number=None,
            timezone_=payload.timezone,
        )
        await self.session.commit()
        return UserResponse.model_validate(user)

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_username(payload.username)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username atau password salah.",
            )
        return self._issue_tokens(str(user.id))

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="Refresh token tidak valid.") from exc
        user = await self.users.get(uuid.UUID(payload["sub"]))
        if not user:
            raise HTTPException(status_code=401, detail="Pengguna tidak ditemukan.")
        return self._issue_tokens(str(user.id))

    @staticmethod
    def _issue_tokens(subject: str) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(subject),
            refresh_token=create_refresh_token(subject),
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
        return user

    async def update_profile(
        self, user_id: uuid.UUID, payload: ProfileUpdate
    ) -> ProfileUpdate:
        profile = await self.profiles.upsert(
            user_id,
            display_name=payload.display_name,
            phone_number=payload.phone_number,
            timezone_=payload.timezone,
        )
        await self.session.commit()
        return ProfileUpdate(
            display_name=profile.display_name,
            phone_number=profile.phone_number,
            timezone=profile.timezone,
        )

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=timezone.utc)
