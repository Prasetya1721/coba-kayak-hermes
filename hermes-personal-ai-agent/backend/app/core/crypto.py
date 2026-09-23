"""Field-level encryption (AES-256-GCM) for data at rest (PRD §7.3).

Two modes:
  1. Vault (preferred): a Key Encryption Key (KEK) lives in HashiCorp Vault;
     each encryption uses a fresh Data Encryption Key (DEK) that is itself
     wrapped by Vault's transit engine.
  2. Fallback (dev only): a single AES-256 key from `FIELD_ENCRYPTION_KEY`.

Payload format (portable across modes):
    version(1 byte) || nonce(12) || ciphertext || tag(16)
Stored as BYTEA in Postgres so `pgcrypto`-based policies can coexist.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_VERSION_LOCAL = 0x01
_VERSION_VAULT = 0x02
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256


class EncryptionError(RuntimeError):
    pass


# --- Key material -------------------------------------------------------------


def _local_key() -> bytes:
    raw = settings.field_encryption_key
    if not raw:
        raise EncryptionError(
            "FIELD_ENCRYPTION_KEY is not set and Vault is unavailable"
        )
    try:
        key = base64.b64decode(raw)
    except Exception:
        # Allow raw 32-char strings in development.
        key = raw.encode("utf-8")
    if len(key) != _KEY_LEN:
        raise EncryptionError("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


class VaultTransit:
    """Minimal HashiCorp Vault transit client (lazy connection)."""

    def __init__(self) -> None:
        self._client = None

    def _connect(self):
        if self._client is not None:
            return self._client
        import hvac

        client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        if not client.is_authenticated():
            raise EncryptionError("Vault authentication failed")
        self._client = client
        return client

    def available(self) -> bool:
        if not settings.vault_token:
            return False
        try:
            client = self._connect()
            client.secrets.transit.read_key(name=f"{settings.vault_path_prefix}-kek") \
                if False else None
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("vault_unavailable", error=str(exc))
            return False

    def wrap_key(self, dek: bytes) -> bytes:
        client = self._connect()
        key_name = f"{settings.vault_path_prefix}-kek"
        try:
            client.secrets.transit.read_key(name=key_name)
        except Exception:
            client.secrets.transit.create_key(name=key_name)
        res = client.secrets.transit.encrypt_data(
            name=key_name,
            plaintext=base64.b64encode(dek).decode("ascii"),
        )
        return res["data"]["ciphertext"].encode("utf-8")

    def unwrap_key(self, wrapped: bytes) -> bytes:
        client = self._connect()
        key_name = f"{settings.vault_path_prefix}-kek"
        res = client.secrets.transit.decrypt_data(
            name=key_name,
            ciphertext=wrapped.decode("utf-8"),
        )
        return base64.b64decode(res["data"]["plaintext"])


_vault = VaultTransit()


def vault_enabled() -> bool:
    if settings.vault_required:
        return True
    return bool(settings.vault_token) and settings.environment != "test"


# --- Public API ---------------------------------------------------------------


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 string, returning opaque bytes."""
    if plaintext is None:
        raise EncryptionError("cannot encrypt None")
    data = plaintext.encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)

    if vault_enabled():
        try:
            dek = os.urandom(_KEY_LEN)
            wrapped = _vault.wrap_key(dek)
            ct = AESGCM(dek).encrypt(nonce, data, None)
            # wrapped_len(2) || wrapped || nonce || ct
            return (
                bytes([_VERSION_VAULT])
                + len(wrapped).to_bytes(2, "big")
                + wrapped
                + nonce
                + ct
            )
        except Exception as exc:  # noqa: BLE001
            if settings.vault_required:
                raise EncryptionError(f"Vault encryption failed: {exc}") from exc
            log.warning("vault_encrypt_fallback", error=str(exc))

    ct = AESGCM(_local_key()).encrypt(nonce, data, None)
    return bytes([_VERSION_LOCAL]) + nonce + ct


def decrypt(payload: bytes) -> str:
    """Decrypt bytes produced by :func:`encrypt`."""
    if not payload:
        raise EncryptionError("empty ciphertext")
    version = payload[0]

    if version == _VERSION_LOCAL:
        nonce, ct = payload[1 : 1 + _NONCE_LEN], payload[1 + _NONCE_LEN :]
        data = AESGCM(_local_key()).decrypt(nonce, ct, None)
        return data.decode("utf-8")

    if version == _VERSION_VAULT:
        wlen = int.from_bytes(payload[1:3], "big")
        wrapped = payload[3 : 3 + wlen]
        rest = payload[3 + wlen :]
        nonce, ct = rest[:_NONCE_LEN], rest[_NONCE_LEN:]
        dek = _vault.unwrap_key(wrapped)
        data = AESGCM(dek).decrypt(nonce, ct, None)
        return data.decode("utf-8")

    raise EncryptionError(f"unknown ciphertext version: {version}")


# --- pgcrypto parity helpers --------------------------------------------------
# These let an operator query/decrypt using SQL if they hold the sym key.


def pgcrypto_sym_key() -> str:
    """Return the symmetric key used for pgp_sym_encrypt in local mode."""
    return base64.b64encode(_local_key()).decode("ascii")


def encrypt_bytes_deterministic(data: bytes, key: bytes | None = None) -> bytes:
    """AES-256-CBC with a fixed IV for indexing/search needs.

    NOTE: deterministic encryption leaks equality. Only use where a lookup
    index is required; prefer :func:`encrypt` for log content.
    """
    key = key or _local_key()
    iv = b"\x00" * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    pad = 16 - (len(data) % 16 or 16)
    padded = data + bytes([pad]) * pad
    return enc.update(padded) + enc.finalize() + iv
