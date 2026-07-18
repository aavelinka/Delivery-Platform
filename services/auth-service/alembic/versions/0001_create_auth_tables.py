"""create auth tables

Revision ID: 0001_create_auth_tables
Revises:
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_auth_tables"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    user_role = sa.Enum(
        "customer",
        "courier",
        "admin",
        name="userrole",
        native_enum=False,
        length=32,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_refresh_tokens_user_created_at",
        "refresh_tokens",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_created_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
