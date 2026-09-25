"""Tests for LLM model failover and manual switching."""

from __future__ import annotations

import pytest

from app.services.agent import llm


class TestModelChain:
    def test_chain_dedupes_and_orders(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "mr-vip")
        monkeypatch.setattr(
            llm.settings, "llm_model_fallbacks", "mr-vip,deepseek-v4.1-flash, mr-vip,hy3"
        )
        assert llm.settings.llm_model_chain == ["mr-vip", "deepseek-v4.1-flash", "hy3"]

    def test_chain_single_when_no_fallbacks(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "solo")
        monkeypatch.setattr(llm.settings, "llm_model_fallbacks", "")
        assert llm.settings.llm_model_chain == ["solo"]


class TestFailoverState:
    def setup_method(self):
        llm.clear_cooldown()
        llm._active_override = None

    def test_mark_failed_puts_on_cooldown(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "m1")
        monkeypatch.setattr(llm.settings, "llm_model_fallbacks", "m2")
        monkeypatch.setattr(llm.settings, "llm_cooldown_seconds", 60)
        llm.mark_model_failed("m1")
        assert llm.active_model() == "m2"

    def test_all_cooling_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "m1")
        monkeypatch.setattr(llm.settings, "llm_model_fallbacks", "m2")
        llm.mark_model_failed("m1")
        llm.mark_model_failed("m2")
        assert llm.active_model() == "m1"  # default anyway

    def test_manual_switch(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "m1")
        monkeypatch.setattr(llm.settings, "llm_model_fallbacks", "m2,m3")
        llm.set_active_model("m3")
        assert llm.active_model() == "m3"
        # switching clears its cooldown
        assert "m3" not in llm.cooldown_snapshot()

    def test_set_empty_model_rejected(self):
        with pytest.raises(llm.LLMConfigError):
            llm.set_active_model("   ")

    def test_available_models_shape(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "m1")
        monkeypatch.setattr(llm.settings, "llm_model_fallbacks", "m2")
        monkeypatch.setattr(llm.settings, "llm_cooldown_seconds", 60)
        llm.mark_model_failed("m1")
        info = llm.available_models()
        assert info[0]["model"] == "m1"
        assert info[0]["active"] is False
        assert info[0]["cooldown_seconds"] > 0
        assert info[1]["model"] == "m2"
        assert info[1]["active"] is True

    def test_clear_cooldown(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "openai_model", "m1")
        llm.mark_model_failed("m1")
        assert llm.cooldown_snapshot()
        llm.clear_cooldown()
        assert llm.cooldown_snapshot() == {}


class TestRetryableDetection:
    @pytest.mark.parametrize(
        "message",
        [
            "Error code: 403 - authentication_error",
            "429 rate limit exceeded",
            "404 model_not_found",
            "request timed out",
            "connection error",
        ],
    )
    def test_retryable(self, message):
        assert llm.is_retryable_error(RuntimeError(message))

    def test_not_retryable(self):
        assert not llm.is_retryable_error(ValueError("bad input shape"))


class TestAgentFailover:
    @pytest.mark.asyncio
    async def test_agent_switches_model_on_quota(self, monkeypatch):
        from unittest.mock import AsyncMock

        from app.services.agent import agent_service as svc

        monkeypatch.setattr(svc.settings, "openai_model", "dead")
        monkeypatch.setattr(svc.settings, "llm_model_fallbacks", "alive")
        llm.clear_cooldown()
        llm._active_override = None

        attempts: list[str] = []

        def fake_build(model, streaming=False):
            attempts.append(model)
            return AsyncMock()

        async def fake_run(model, *args, **kwargs):
            if attempts[-1] == "dead":
                raise svc.LLMCallError("Error code: 403 - authentication_error")
            return svc.AgentResult(reply="ok")

        monkeypatch.setattr(svc, "build_chat_model_for", fake_build)
        monkeypatch.setattr(
            svc.AgentService, "_run_agent_with_model", staticmethod(fake_run)
        )

        db = AsyncMock()
        agent = svc.AgentService(db)
        result = await agent._run_agent([])
        assert result.reply == "ok"
        assert attempts == ["dead", "alive"]
        assert "dead" in llm.cooldown_snapshot()

    @pytest.mark.asyncio
    async def test_non_retryable_error_bubbles(self, monkeypatch):
        from unittest.mock import AsyncMock

        from app.services.agent import agent_service as svc

        monkeypatch.setattr(svc.settings, "openai_model", "m1")
        monkeypatch.setattr(svc.settings, "llm_model_fallbacks", "m2")
        llm.clear_cooldown()
        llm._active_override = None

        def fake_build(model, streaming=False):
            return AsyncMock()

        async def fake_run(model, *args, **kwargs):
            raise svc.LLMCallError("ValueError: bad schema")

        monkeypatch.setattr(svc, "build_chat_model_for", fake_build)
        monkeypatch.setattr(
            svc.AgentService, "_run_agent_with_model", staticmethod(fake_run)
        )

        db = AsyncMock()
        agent = svc.AgentService(db)
        with pytest.raises(svc.LLMCallError):
            await agent._run_agent([])
