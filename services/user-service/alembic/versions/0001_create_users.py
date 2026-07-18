"""create user profile tables

Revision ID: 0001_create_users
Revises:
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_users"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_profiles_email", "user_profiles", ["email"])

    op.create_table(
        "user_addresses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=False),
        sa.Column("street", sa.String(length=255), nullable=False),
        sa.Column("building", sa.String(length=64), nullable=True),
        sa.Column("apartment", sa.String(length=64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_addresses_user_id", "user_addresses", ["user_id"])
    op.create_index(
        "ix_user_addresses_user_default",
        "user_addresses",
        ["user_id", "is_default"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_addresses_user_default", table_name="user_addresses")
    op.drop_index("ix_user_addresses_user_id", table_name="user_addresses")
    op.drop_table("user_addresses")
    op.drop_index("ix_user_profiles_email", table_name="user_profiles")
    op.drop_table("user_profiles")
