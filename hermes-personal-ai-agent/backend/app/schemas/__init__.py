"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- Auth ---------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)
    # UU PDP: explicit consent is mandatory.
    consent: bool = Field(description="Pengguna menyetujui pemrosesan data sesuai UU PDP")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: EmailStr
    consent_given: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=50)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    display_name: str | None = None
    phone_number: str | None = None
    timezone: str | None = None


# --- Chat ---------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime | None = None
    detections: list[str] | None = None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    platform_chat_id: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[ChatMessage]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    reply: str
    scrubbed: bool
    detections: list[str] = []


# --- Templates ----------------------------------------------------------------


class TemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = None
    command_pattern: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=50)


class TemplateUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    description: str | None = None
    command_pattern: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=50)


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    command_pattern: str
    category: str | None = None
    is_builtin: bool
    created_at: datetime


# --- Notifications ------------------------------------------------------------


class NotificationCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    platform: Literal["whatsapp", "telegram"]
    schedule_cron: str | None = Field(default=None, max_length=100)
    run_at: datetime | None = None
    target_chat_id: str | None = None

    def model_post_init(self, __context) -> None:  # noqa: D105
        if not self.schedule_cron and not self.run_at:
            raise ValueError("Either schedule_cron or run_at must be provided")


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: str
    schedule_cron: str | None = None
    run_at: datetime | None = None
    platform: str
    target_chat_id: str | None = None
    next_run: datetime | None = None
    active: bool
    created_at: datetime


# --- Credentials --------------------------------------------------------------


class CredentialCreate(BaseModel):
    service_name: str = Field(min_length=1, max_length=50)
    token: str = Field(min_length=1, max_length=8000)


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_name: str
    created_at: datetime


# --- Onboarding ---------------------------------------------------------------


class OnboardingStatus(BaseModel):
    completed: bool
    steps: dict[str, bool]
    next_step: str | None = None


# --- Privacy ------------------------------------------------------------------


class DataExportResponse(BaseModel):
    exported_at: datetime
    profile: ProfileResponse | None
    templates: list[TemplateResponse]
    notifications: list[NotificationResponse]
    sessions: list[ChatSessionResponse]
    chat_messages: dict[str, list[ChatMessage]]


class DeleteDataResponse(BaseModel):
    deleted: bool
    detail: str


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
