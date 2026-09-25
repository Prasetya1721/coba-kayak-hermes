"""Tests for the chat session contract, credential resolver, and rate limits."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.schemas import ChatRequest
from app.services.agent.agent_service import AgentService, SessionNotFoundError
from app.services.credentials import CredentialNotFoundError, resolve_user_credential


class TestChatRequestContract:
    def test_session_id_is_optional(self):
        req = ChatRequest(message="halo")
        assert req.session_id is None

    def test_session_id_must_be_uuid(self):
        with pytest.raises(Exception):
            ChatRequest(message="halo", session_id="bukan-uuid")

    def test_session_id_accepts_uuid(self):
        sid = uuid.uuid4()
        req = ChatRequest(message="halo", session_id=sid)
        assert req.session_id == sid


class TestAgentSessionOwnership:
    @pytest.mark.asyncio
    async def test_unknown_session_raises(self):
        db = AsyncMock()
        service = AgentService(db)
        service.sessions.get_owned = AsyncMock(return_value=None)
        service.sessions.get_or_create = AsyncMock()

        with pytest.raises(SessionNotFoundError):
            await service.handle_message(
                user_id=uuid.uuid4(),
                platform="telegram",
                platform_chat_id="web:x",
                message="halo",
                session_id=uuid.uuid4(),
            )
        service.sessions.get_or_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_known_session_is_used(self, monkeypatch):
        from app.services.agent import agent_service as agent_module

        db = AsyncMock()
        service = AgentService(db)
        owned = AsyncMock()
        owned.id = uuid.uuid4()
        service.sessions.get_owned = AsyncMock(return_value=owned)
        service.sessions.get_or_create = AsyncMock()
        service.logs.append = AsyncMock()
        service.logs.recent = AsyncMock(return_value=[])
        service.memory.recall_block = AsyncMock(return_value="")

        from app.services.agent.agent_service import AgentResult

        monkeypatch.setattr(
            agent_module, "llm_is_configured", lambda: False
        )

        session_id, result = await service.handle_message(
            user_id=uuid.uuid4(),
            platform="telegram",
            platform_chat_id="web:x",
            message="halo",
            session_id=owned.id,
        )
        assert session_id == owned.id
        assert isinstance(result, AgentResult)
        service.sessions.get_or_create.assert_not_called()


class TestCredentialResolver:
    @pytest.mark.asyncio
    async def test_missing_credential_raises(self):
        db = AsyncMock()
        import app.services.credentials as creds_module

        real_repo = creds_module.CredentialRepository

        class _Repo:
            def __init__(self, session):
                self.session = session

            async def get_service_token(self, user_id, service_name):
                return None

        creds_module.CredentialRepository = _Repo
        try:
            with pytest.raises(CredentialNotFoundError):
                await resolve_user_credential(db, uuid.uuid4(), "ssh_rumah")
        finally:
            creds_module.CredentialRepository = real_repo

    @pytest.mark.asyncio
    async def test_blank_service_name_raises(self):
        with pytest.raises(CredentialNotFoundError):
            await resolve_user_credential(AsyncMock(), uuid.uuid4(), "   ")

    @pytest.mark.asyncio
    async def test_ssh_impl_uses_resolver(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        async def fake_resolver(ref: str) -> str:
            assert ref == "ssh_rumah"
            return "s3cr3t-password"

        monkeypatch.setattr(registry, "_resolver", fake_resolver)

        captured: dict = {}

        async def fake_ssh(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(registry.device, "execute_ssh", fake_ssh)

        out = await registry._ssh_impl(
            host="h", username="u", command="uptime", credential_ref="ssh_rumah"
        )
        assert out == "ok"
        assert captured["password"] == "s3cr3t-password"
        assert captured.get("private_key") is None

    @pytest.mark.asyncio
    async def test_ssh_impl_detects_private_key(self, monkeypatch):
        from app.services.agent import tool_registry as registry

        async def fake_resolver(ref: str) -> str:
            return "-----BEGIN RSA PRIVATE KEY-----\nabc"

        monkeypatch.setattr(registry, "_resolver", fake_resolver)

        captured: dict = {}

        async def fake_ssh(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(registry.device, "execute_ssh", fake_ssh)

        await registry._ssh_impl(
            host="h", username="u", command="uptime", credential_ref="ssh_key"
        )
        assert captured.get("password") is None
        assert captured["private_key"].startswith("-----BEGIN")


class TestRateLimitConfig:
    def test_limiter_has_default_limits(self):
        from app.core.rate_limit import AUTH_LIMIT, WEBHOOK_LIMIT, limiter

        assert AUTH_LIMIT == "5/minute"
        assert "minute" in WEBHOOK_LIMIT
        assert limiter._default_limits

    def test_main_wires_middleware(self):
        from fastapi import FastAPI

        from app.main import create_app

        test_app = create_app()
        assert isinstance(test_app, FastAPI)
        assert test_app.state.limiter is not None
