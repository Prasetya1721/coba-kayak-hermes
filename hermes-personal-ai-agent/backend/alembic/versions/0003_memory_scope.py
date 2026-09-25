"""memory scope + session summaries

Revision ID: 0003_memory_scope
Revises: 0002_memories
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_memory_scope"
down_revision = "0002_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_memories",
        sa.Column("scope", sa.String(80), nullable=False, server_default="global"),
    )
    op.create_index("ix_memories_user_scope", "user_memories", ["user_id", "scope"])

    op.create_table(
        "session_summaries",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("messages_covered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_summaries_session", "session_summaries", ["session_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_summaries_session", table_name="session_summaries")
    op.drop_table("session_summaries")
    op.drop_index("ix_memories_user_scope", table_name="user_memories")
    op.drop_column("user_memories", "scope")
