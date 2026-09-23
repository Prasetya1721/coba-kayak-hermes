"""User, Profile, and Credential repositories."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.db.models import Credential, Profile, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        consent: bool,
    ) -> User:
        user = User(
            username=username,
            email=email.lower(),
            password_hash=password_hash,
            consent_given=consent,
            consent_at=datetime.now(tz=timezone.utc) if consent else None,
        )
        return await self.add(user)


class ProfileRepository(BaseRepository[Profile]):
    model = Profile

    async def get_by_user(self, user_id: uuid.UUID) -> Profile | None:
        return await self.session.get(Profile, user_id)

    async def upsert(
        self,
        user_id: uuid.UUID,
        *,
        display_name: str | None,
        phone_number: str | None,
        timezone_: str | None,
    ) -> Profile:
        profile = await self.get_by_user(user_id)
        if profile is None:
            profile = Profile(
                user_id=user_id,
                display_name=display_name,
                phone_number=phone_number,
                timezone=timezone_,
            )
            await self.add(profile)
            return profile
        if display_name is not None:
            profile.display_name = display_name
        if phone_number is not None:
            profile.phone_number = phone_number
        if timezone_ is not None:
            profile.timezone = timezone_
        await self.session.flush()
        return profile


class CredentialRepository(BaseRepository[Credential]):
    model = Credential

    async def get_service_token(
        self, user_id: uuid.UUID, service_name: str
    ) -> Credential | None:
        stmt = select(Credential).where(
            Credential.user_id == user_id,
            Credential.service_name == service_name,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self, user_id: uuid.UUID, service_name: str, encrypted_token: bytes
    ) -> Credential:
        existing = await self.get_service_token(user_id, service_name)
        if existing:
            existing.encrypted_token = encrypted_token
            await self.session.flush()
            return existing
        cred = Credential(
            user_id=user_id,
            service_name=service_name,
            encrypted_token=encrypted_token,
        )
        return await self.add(cred)

    async def delete_by_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(Credential).where(Credential.user_id == user_id)
        )
