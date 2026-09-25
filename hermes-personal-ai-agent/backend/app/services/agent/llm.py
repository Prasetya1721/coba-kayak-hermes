"""LLM provider factory (OpenAI GPT-4o or Anthropic Claude)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


class LLMConfigError(RuntimeError):
    pass


def build_chat_model(*, streaming: bool = False) -> BaseChatModel:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMConfigError("OPENAI_API_KEY belum dikonfigurasi.")
        from langchain_openai import ChatOpenAI

        kwargs: dict = {
            "model": settings.openai_model,
            "api_key": settings.openai_api_key,
            "temperature": settings.llm_temperature,
            "streaming": streaming,
            # Fail fast on dead gateways instead of hanging the reply.
            "timeout": settings.llm_request_timeout,
            "max_retries": settings.llm_max_retries,
        }
        # Custom OpenAI-compatible gateway (e.g. https://modelrouter.id/v1).
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMConfigError("ANTHROPIC_API_KEY belum dikonfigurasi.")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=settings.llm_temperature,
            streaming=streaming,
            timeout=settings.llm_request_timeout,
            max_retries=settings.llm_max_retries,
        )

    raise LLMConfigError(f"LLM provider tidak dikenal: {settings.llm_provider}")


def llm_is_configured() -> bool:
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.llm_provider == "anthropic":
        return bool(settings.anthropic_api_key)
    return False
