"""LLM provider factory with automatic model failover.

Why: single API keys on reseller gateways (ModelRouter, OpenRouter, ...) often
run out of quota or lose access to ONE model while others still work. Instead of
going silent, we try the chain in order:

    OPENAI_MODEL -> LLM_MODEL_FALLBACKS (comma-separated) -> ...

A model that fails with quota/permission/not-found/timeout is put on a short
cooldown and skipped for the next turns. The active model is persisted so a
manual switch (dashboard/API) survives restarts.
"""

from __future__ import annotations

import time

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMConfigError(RuntimeError):
    pass


# --- Failover state (in-process) ----------------------------------------------
# model -> epoch seconds until which it is skipped.
_cooldown: dict[str, float] = {}
_active_override: str | None = None


def _is_cooling(model: str) -> bool:
    until = _cooldown.get(model, 0)
    if until and until <= time.monotonic():
        _cooldown.pop(model, None)
        return False
    return until > 0


def mark_model_failed(model: str) -> None:
    """Put a model on cooldown (called by AgentService after a hard failure)."""
    _cooldown[model] = time.monotonic() + settings.llm_cooldown_seconds
    log.info(
        "llm_model_cooldown",
        model=model,
        seconds=settings.llm_cooldown_seconds,
    )


def clear_cooldown() -> None:
    _cooldown.clear()


def cooldown_snapshot() -> dict[str, int]:
    now = time.monotonic()
    return {
        m: int(until - now)
        for m, until in _cooldown.items()
        if until > now
    }


def active_model() -> str:
    """The model we will try first right now."""
    if _active_override and not _is_cooling(_active_override):
        return _active_override
    for model in settings.llm_model_chain:
        if not _is_cooling(model):
            return model
    # Everything is cooling: fall back to the configured default anyway.
    return settings.openai_model


def set_active_model(model: str) -> str:
    """Manual switch (persists for the session)."""
    global _active_override
    model = (model or "").strip()
    if not model:
        raise LLMConfigError("Nama model kosong.")
    _active_override = model
    _cooldown.pop(model, None)
    log.info("llm_model_switched", model=model)
    return model


def available_models() -> list[str]:
    """Configured chain with cooldown status (for the settings UI)."""
    active = active_model()
    cooling = cooldown_snapshot()
    return [
        {
            "model": m,
            "active": m == active,
            "cooldown_seconds": cooling.get(m, 0),
        }
        for m in settings.llm_model_chain
    ]


# --- Model construction --------------------------------------------------------


def _build_openai(model: str, streaming: bool) -> BaseChatModel:
    if not settings.openai_api_key:
        raise LLMConfigError("OPENAI_API_KEY belum dikonfigurasi.")
    from langchain_openai import ChatOpenAI

    kwargs: dict = {
        "model": model,
        "api_key": settings.openai_api_key,
        "temperature": settings.llm_temperature,
        "streaming": streaming,
        "timeout": settings.llm_request_timeout,
        # Retries handled by our own failover chain, not by the client.
        "max_retries": 0,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)


def _build_anthropic(streaming: bool) -> BaseChatModel:
    if not settings.anthropic_api_key:
        raise LLMConfigError("ANTHROPIC_API_KEY belum dikonfigurasi.")
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        temperature=settings.llm_temperature,
        streaming=streaming,
        timeout=settings.llm_request_timeout,
        max_retries=0,
    )


def build_chat_model(*, streaming: bool = False) -> BaseChatModel:
    """Build a client for the currently active (non-cooling) model."""
    if settings.llm_provider == "anthropic":
        return _build_anthropic(streaming=streaming)
    if settings.llm_provider == "openai":
        return _build_openai(active_model(), streaming=streaming)
    raise LLMConfigError(f"LLM provider tidak dikenal: {settings.llm_provider}")


def build_chat_model_for(model: str, *, streaming: bool = False) -> BaseChatModel:
    if settings.llm_provider == "anthropic":
        return _build_anthropic(streaming=streaming)
    return _build_openai(model, streaming=streaming)


def llm_is_configured() -> bool:
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.llm_provider == "anthropic":
        return bool(settings.anthropic_api_key)
    return False


def is_retryable_error(exc: Exception) -> bool:
    """True when the model itself is at fault (quota/perm/missing/timeout)."""
    text = str(exc).lower()
    markers = (
        "403", "429", "404", "401",
        "authentication", "permission", "quota", "rate limit", "rate_limit",
        "not found", "model_not_found", "insufficient",
        "timeout", "timed out", "connection", "unauthorized",
    )
    return any(m in text for m in markers)
