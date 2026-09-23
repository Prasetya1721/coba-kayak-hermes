"""Integration tests for the message-gateway webhooks (no live DB)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import webhooks
from app.core import rate_limit


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Stub outbound calls and agent processing to isolate webhook handling.
    async def fake_process(db, *, platform, platform_chat_id, text):
        fake_process.calls.append((platform, platform_chat_id, text))
        return "OK"

    fake_process.calls = []  # type: ignore[attr-defined]

    async def fake_send_telegram(chat_id, text):
        return True

    async def fake_send_whatsapp(to, text):
        return True

    monkeypatch.setattr(webhooks, "process_inbound", fake_process)
    monkeypatch.setattr(webhooks, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(webhooks, "send_whatsapp", fake_send_whatsapp)

    # Generous rate limits for tests (per-test app instances share state).
    monkeypatch.setattr(rate_limit, "WEBHOOK_LIMIT", "1000/minute")

    # Provide a fake session context manager.
    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(webhooks, "SessionLocal", lambda: _FakeSession())

    app = FastAPI()
    app.state.limiter = webhooks.limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhooks.router, prefix="/api")
    return TestClient(app)


class TestTelegramWebhook:
    def test_rejects_bad_secret(self, client, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "telegram_webhook_secret", "expected")
        resp = client.post(
            "/api/webhooks/telegram",
            json={"message": {"chat": {"id": 1}, "text": "halo"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert resp.status_code == 403

    def test_rejects_when_no_secret_configured(self, client, monkeypatch):
        """Fail closed: an unconfigured webhook accepts nothing."""
        monkeypatch.setattr(webhooks.settings, "telegram_webhook_secret", "")
        resp = client.post(
            "/api/webhooks/telegram",
            json={"message": {"chat": {"id": 1}, "text": "halo"}},
        )
        assert resp.status_code == 403

    def test_accepts_valid_update(self, client, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "telegram_webhook_secret", "expected")
        resp = client.post(
            "/api/webhooks/telegram",
            json={"message": {"chat": {"id": 42}, "text": "halo hermes"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "expected"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_rejects_malformed_json(self, client, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "telegram_webhook_secret", "expected")
        resp = client.post(
            "/api/webhooks/telegram",
            content=b"not-json",
            headers={
                "Content-Type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "expected",
            },
        )
        assert resp.status_code == 400


class TestWhatsAppWebhook:
    def test_accepts_twilio_form_payload(self, client, monkeypatch):
        # Unsigned dev mode: provider "none" skips signature enforcement.
        monkeypatch.setattr(webhooks.settings, "whatsapp_provider", "none")
        resp = client.post(
            "/api/webhooks/whatsapp",
            data={"From": "whatsapp:+628123456789", "Body": "test pesan"},
        )
        assert resp.status_code == 200
        assert "Response" in resp.text

    def test_rejects_missing_twilio_signature(self, client, monkeypatch):
        """A missing signature must be rejected, not silently skipped."""
        monkeypatch.setattr(webhooks.settings, "whatsapp_provider", "twilio")
        monkeypatch.setattr(webhooks.settings, "twilio_auth_token", "real-token")
        resp = client.post(
            "/api/webhooks/whatsapp",
            data={"From": "whatsapp:+6281234", "Body": "hi"},
        )
        assert resp.status_code == 403

    def test_rejects_bad_twilio_signature(self, client, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "whatsapp_provider", "twilio")
        monkeypatch.setattr(webhooks.settings, "twilio_auth_token", "real-token")
        resp = client.post(
            "/api/webhooks/whatsapp",
            data={"From": "whatsapp:+6281234", "Body": "hi"},
            headers={"X-Twilio-Signature": "invalid-signature"},
        )
        assert resp.status_code == 403

    def test_baileys_json_payload(self, client, monkeypatch):
        monkeypatch.setattr(webhooks.settings, "whatsapp_provider", "baileys")
        resp = client.post(
            "/api/webhooks/whatsapp",
            json={"from": "628123456789", "text": "halo via baileys"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
