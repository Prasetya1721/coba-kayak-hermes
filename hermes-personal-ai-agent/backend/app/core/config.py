"""Application settings loaded from environment variables.

Every credential comes from the environment (or Vault at runtime); nothing is
hard-coded. See `.env.example` at the repo root for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime ---
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    app_name: str = "Hermes Personal AI Agent"
    api_prefix: str = "/api"

    # --- Backend ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # --- Database / cache ---
    database_url: str = "postgresql+asyncpg://hermes:hermes@localhost:5432/hermes"
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # --- Field encryption ---
    field_encryption_key: str = ""

    # --- Vault ---
    vault_addr: str = "http://localhost:8200"
    vault_token: str = ""
    vault_mount_point: str = "secret"
    vault_path_prefix: str = "hermes"
    vault_required: bool = False

    # --- AI ---
    llm_provider: Literal["openai", "anthropic"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    llm_temperature: float = 0.2
    short_term_memory_size: int = 10

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""

    # --- WhatsApp ---
    whatsapp_provider: Literal["twilio", "baileys", "none"] = "none"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    baileys_gateway_url: str = "http://localhost:3100"
    baileys_gateway_token: str = ""

    # --- Web search ---
    search_provider: Literal["serpapi", "brave", "none"] = "none"
    serpapi_api_key: str = ""
    brave_search_api_key: str = ""

    # --- Device management ---
    ssh_command_whitelist: str = "uptime,df -h,free -m,ls,cat"
    ssh_connect_timeout_seconds: int = 10
    ssh_command_timeout_seconds: int = 30

    # --- Web management ---
    github_token: str = ""
    vercel_token: str = ""

    # --- Scheduler ---
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Jakarta"
    scheduler_poll_seconds: int = 30

    # --- Rate limiting ---
    rate_limit_per_minute: int = 60
    rate_limit_webhook_per_minute: int = 120

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ssh_whitelist_list(self) -> list[str]:
        return [c.strip() for c in self.ssh_command_whitelist.split(",") if c.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def assert_production_safety(self) -> None:
        """Fail fast when insecure defaults are used in production."""
        if not self.is_production:
            return
        problems: list[str] = []
        if "change-me" in self.jwt_secret_key or len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY must be a strong random value (>=32 chars)")
        if not self.field_encryption_key:
            problems.append("FIELD_ENCRYPTION_KEY must be set for data-at-rest encryption")
        if self.debug:
            problems.append("DEBUG must be false in production")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
