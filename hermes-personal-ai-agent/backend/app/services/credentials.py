"""Credential resolver: decrypt per-user service tokens from the KMS store.

Only exact service-name matches are supported; there is no listing or partial
matching (prevents confused-deputy lookups). Decrypted values stay in memory
and are never logged.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.repositories.users import CredentialRepository


class CredentialNotFoundError(ValueError):
    pass


async def resolve_user_credential(
    db: AsyncSession, user_id: uuid.UUID, service_name: str
) -> str:
    """Return the plaintext token for `service_name` owned by `user_id`."""
    service_name = (service_name or "").strip()
    if not service_name:
        raise CredentialNotFoundError("Nama kredensial kosong.")

    row = await CredentialRepository(db).get_service_token(user_id, service_name)
    if row is None:
        raise CredentialNotFoundError(
            f"Kredensial '{service_name}' tidak ditemukan. "
            "Simpan dulu via POST /api/credentials atau halaman Onboarding."
        )
    try:
        return decrypt(row.encrypted_token)
    except Exception as exc:  # noqa: BLE001
        raise CredentialNotFoundError(
            f"Kredensial '{service_name}' tidak dapat didekripsi."
        ) from exc
