"""create orders tables

Revision ID: 0001_create_orders
Revises:
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_orders"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    order_status = sa.Enum(
        "created",
        "waiting_for_courier",
        "courier_assigned",
        "in_delivery",
        "delivered",
        "cancelled",
        name="orderstatus",
        native_enum=False,
        length=32,
    )
    order_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("courier_id", sa.Uuid(), nullable=True),
        sa.Column("pickup_address", sa.Text(), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_courier_id", "orders", ["courier_id"])
    op.create_index("ix_orders_status_created_at", "orders", ["status", "created_at"])

    op.create_table(
        "order_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("previous_status", order_status, nullable=True),
        sa.Column("new_status", order_status, nullable=True),
        sa.Column("changed_by", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])
    op.create_index("ix_order_events_event_type", "order_events", ["event_type"])
    op.create_index("ix_order_events_order_created_at", "order_events", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_order_events_order_created_at", table_name="order_events")
    op.drop_index("ix_order_events_event_type", table_name="order_events")
    op.drop_index("ix_order_events_order_id", table_name="order_events")
    op.drop_table("order_events")

    op.drop_index("ix_orders_status_created_at", table_name="orders")
    op.drop_index("ix_orders_courier_id", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_table("orders")
