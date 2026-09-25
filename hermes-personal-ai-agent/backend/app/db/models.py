"""SQLAlchemy models mirroring the PRD schema (PostgreSQL 16)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # UU PDP consent (PRD §7.4)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["Profile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    templates: Mapped[list["CommandTemplate"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["ScheduledNotification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["UserMemory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base):
    """Personal identity, stored separately from operational chat data."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str | None] = mapped_column(String(50))

    user: Mapped[User] = relationship(back_populates="profile")


class ChatSession(Base):
    """Anonymous session linking a platform chat to a user."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint("platform IN ('whatsapp', 'telegram')", name="ck_session_platform"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="sessions")
    logs: Mapped[list["ChatLog"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatLog(Base):
    """Conversation log; `content_encrypted` holds AES-256-GCM ciphertext."""

    __tablename__ = "chat_logs"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_log_role"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Optional non-sensitive metadata (tool name, detections) for audits.
    meta: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[ChatSession] = relationship(back_populates="logs")


class CommandTemplate(Base):
    __tablename__ = "command_templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    command_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="templates")


class ScheduledNotification(Base):
    __tablename__ = "scheduled_notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    target_chat_id: Mapped[str | None] = mapped_column(String(255))
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="notifications")


class Credential(Base):
    """Per-service tokens, encrypted via Vault/KMS (PRD §7.3)."""

    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="credentials")


class UserMemory(Base):
    """Long-term facts about the user, encrypted at rest (PRD memory permanen).

    Examples: "nama saya Budi", "ulang tahun 5 Mei", "suka kopi tubruk",
    "punya server di 192.168.1.10". Captured explicitly ("ingat ya ...") or
    extracted from conversation; recalled at the start of every turn.
    """

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Short label: "nama", "ulang_tahun", "preferensi", "perangkat", ...
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    # AES-256-GCM ciphertext of the fact (value never stored in plaintext).
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Where it came from: "explicit" (user said "ingat") or "extracted".
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="explicit")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="memories")


class AuditEvent(Base):
    """Append-only audit trail for security-relevant actions."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
