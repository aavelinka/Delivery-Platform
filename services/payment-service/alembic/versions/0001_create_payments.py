"""create payments tables

Revision ID: 0001_create_payments
Revises:
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_payments"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    payment_status = sa.Enum(
        "pending",
        "confirmed",
        "failed",
        "refunded",
        name="paymentstatus",
        native_enum=False,
        length=32,
    )
    payment_status.create(op.get_bind(), checkfirst=True)

    payment_method = sa.Enum(
        "card",
        "sbp",
        "apple_pay",
        "google_pay",
        name="paymentmethod",
        native_enum=False,
        length=32,
    )
    payment_method.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("payment_method", payment_method, nullable=False),
        sa.Column("provider_reference", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_created_at", "payments", ["created_at"])
    op.create_index("ix_payments_provider_reference", "payments", ["provider_reference"])
    op.create_index("ix_payments_status_created_at", "payments", ["status", "created_at"])

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("previous_status", payment_status, nullable=True),
        sa.Column("new_status", payment_status, nullable=True),
        sa.Column("changed_by", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])
    op.create_index("ix_payment_events_event_type", "payment_events", ["event_type"])
    op.create_index(
        "ix_payment_events_payment_created_at",
        "payment_events",
        ["payment_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment_created_at", table_name="payment_events")
    op.drop_index("ix_payment_events_event_type", table_name="payment_events")
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("ix_payments_status_created_at", table_name="payments")
    op.drop_index("ix_payments_provider_reference", table_name="payments")
    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")
