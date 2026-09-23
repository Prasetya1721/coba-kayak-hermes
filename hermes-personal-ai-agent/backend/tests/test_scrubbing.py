"""Unit tests for the sensitive-data scrubbing middleware."""

from __future__ import annotations

import pytest

from app.middleware.scrubbing import (
    MASK,
    contains_medical,
    scrub_text,
    scrub_text_detailed,
    scrub_value,
)


class TestCreditCard:
    def test_masks_valid_visa_keeping_last4(self):
        out = scrub_text("Kartu saya 4111 1111 1111 1111 tolong simpan")
        assert "4111 1111 1111 1111" not in out
        assert out.endswith("1111 tolong simpan")
        assert "*" in out

    def test_masks_valid_amex_dashed(self):
        out = scrub_text("3782-822463-10005")
        assert "378282246310005" not in out.replace("-", "")

    def test_invalid_luhn_not_masked(self):
        raw = "1234 5678 9012 3456"
        assert scrub_text(raw) == raw


class TestNIK:
    def test_masks_16_digit_nik(self):
        out = scrub_text("NIK saya 3174092705990001 ya")
        assert "3174092705990001" not in out
        assert out.endswith("0001 ya")


class TestSecrets:
    def test_masks_password_assignment(self):
        out = scrub_text("password=SuperSecret123")
        assert "SuperSecret123" not in out
        assert MASK in out

    def test_masks_api_key_colon(self):
        out = scrub_text("api_key: sk-abcdef1234567890")
        assert "sk-abcdef1234567890" not in out

    def test_masks_bearer_token(self):
        out = scrub_text("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6")
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6" not in out

    def test_masks_pem_private_key(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----"
        assert "MIIEow" not in scrub_text(pem)


class TestEmailAndPhone:
    def test_masks_email_partially(self):
        out = scrub_text("email budi@example.com")
        assert "budi@example.com" not in out
        assert "@example.com" in out

    def test_masks_indonesian_phone(self):
        out = scrub_text("hubungi +6281234567890")
        assert "081234567890" not in out.replace("+", "")


class TestMedical:
    def test_flags_medical_content(self):
        assert contains_medical("hasil lab menunjukkan kolesterol tinggi")

    def test_detailed_reports_detections(self):
        result = scrub_text_detailed("password=abc123 dan NIK 3174092705990001")
        assert "secret_assignment" in result.detections
        assert "nik" in result.detections
        assert result.changed


class TestIdempotency:
    @pytest.mark.parametrize(
        "text",
        [
            "password=secret",
            "4111 1111 1111 1111",
            "3174092705990001",
            "budi@example.com",
        ],
    )
    def test_scrub_is_idempotent(self, text):
        once = scrub_text(text)
        twice = scrub_text(once)
        assert once == twice


class TestRecursive:
    def test_scrubs_nested_structures(self):
        payload = {"user": {"note": "password=abc123"}, "items": ["NIK 3174092705990001"]}
        out = scrub_value(payload)
        assert "abc123" not in str(out)
        assert "3174092705990001" not in str(out)


class TestPassthrough:
    def test_clean_text_unchanged(self):
        text = "Tolong buatkan ringkasan artikel tentang Python."
        assert scrub_text(text) == text

    def test_empty_string(self):
        assert scrub_text("") == ""
