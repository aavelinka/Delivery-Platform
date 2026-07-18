"""create notifications table

Revision ID: 0001_create_notifications
Revises:
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_notifications"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    channel = sa.Enum(
        "in_app",
        "email",
        "sms",
        "push",
        "telegram",
        name="notificationchannel",
        native_enum=False,
        length=32,
    )
    status = sa.Enum(
        "created",
        "sent",
        "failed",
        "read",
        name="notificationstatus",
        native_enum=False,
        length=32,
    )
    channel.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("channel", channel, nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_event_type", sa.String(length=128), nullable=True),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("aggregate_type", sa.String(length=64), nullable=True),
        sa.Column("aggregate_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_source_event_type", "notifications", ["source_event_type"])
    op.create_index("ix_notifications_source_event_id", "notifications", ["source_event_id"])
    op.create_index("ix_notifications_aggregate_id", "notifications", ["aggregate_id"])
    op.create_index("ix_notifications_user_created_at", "notifications", ["user_id", "created_at"])
    op.create_index("ix_notifications_status_created_at", "notifications", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_status_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_created_at", table_name="notifications")
    op.drop_index("ix_notifications_aggregate_id", table_name="notifications")
    op.drop_index("ix_notifications_source_event_id", table_name="notifications")
    op.drop_index("ix_notifications_source_event_type", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
