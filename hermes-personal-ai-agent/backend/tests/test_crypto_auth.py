"""Unit tests for AES-256 field encryption and password/JWT helpers."""

from __future__ import annotations

import pytest

from app.core.crypto import decrypt, encrypt, encrypt_bytes_deterministic
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestEncryption:
    def test_roundtrip(self):
        plaintext = "halo, ini pesan rahasia 🔐"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_unicode_and_long(self):
        plaintext = "リマ " * 500
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_ciphertext_is_not_plaintext(self):
        blob = encrypt("super-secret-token")
        assert b"super-secret-token" not in blob
        assert len(blob) > len("super-secret-token")

    def test_nonce_is_random_so_ciphertext_differs(self):
        a = encrypt("same message")
        b = encrypt("same message")
        assert a != b
        assert decrypt(a) == decrypt(b)

    def test_tampering_is_detected(self):
        blob = bytearray(encrypt("integrity check"))
        blob[-1] ^= 0xFF  # flip a ciphertext/tag byte
        with pytest.raises(Exception):
            decrypt(bytes(blob))

    def test_empty_ciphertext_raises(self):
        with pytest.raises(Exception):
            decrypt(b"")

    def test_deterministic_cipher_is_stable(self):
        assert encrypt_bytes_deterministic(b"index-key") == encrypt_bytes_deterministic(
            b"index-key"
        )


class TestPasswords:
    def test_hash_and_verify(self):
        hashed = hash_password("CorrectHorseBattery")
        assert hashed != "CorrectHorseBattery"
        assert verify_password("CorrectHorseBattery", hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("CorrectHorseBattery")
        assert not verify_password("wrong-password", hashed)

    def test_invalid_hash_returns_false(self):
        assert not verify_password("anything", "not-a-hash")


class TestJWT:
    def test_access_token_roundtrip(self):
        token = create_access_token("user-123")
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_type_confusion_rejected(self):
        token = create_access_token("user-123")
        with pytest.raises(Exception):
            decode_token(token, expected_type="refresh")

    def test_tampered_token_rejected(self):
        token = create_access_token("user-123")
        with pytest.raises(Exception):
            decode_token(token + "x", expected_type="access")
