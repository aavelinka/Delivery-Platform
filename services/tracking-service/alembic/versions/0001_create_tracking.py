"""create tracking tables

Revision ID: 0001_create_tracking
Revises:
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_tracking"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracked_orders",
        sa.Column("order_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("courier_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tracked_orders_user_id", "tracked_orders", ["user_id"])
    op.create_index(
        "ix_tracked_orders_courier_user_id",
        "tracked_orders",
        ["courier_user_id"],
    )

    op.create_table(
        "courier_locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("courier_user_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_courier_locations_courier_user_id",
        "courier_locations",
        ["courier_user_id"],
    )
    op.create_index("ix_courier_locations_user_id", "courier_locations", ["user_id"])
    op.create_index("ix_courier_locations_order_id", "courier_locations", ["order_id"])
    op.create_index(
        "ix_locations_order_recorded_at",
        "courier_locations",
        ["order_id", "recorded_at"],
    )
    op.create_index(
        "ix_locations_courier_recorded_at",
        "courier_locations",
        ["courier_user_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_locations_courier_recorded_at", table_name="courier_locations")
    op.drop_index("ix_locations_order_recorded_at", table_name="courier_locations")
    op.drop_index("ix_courier_locations_order_id", table_name="courier_locations")
    op.drop_index("ix_courier_locations_user_id", table_name="courier_locations")
    op.drop_index("ix_courier_locations_courier_user_id", table_name="courier_locations")
    op.drop_table("courier_locations")
    op.drop_index("ix_tracked_orders_courier_user_id", table_name="tracked_orders")
    op.drop_index("ix_tracked_orders_user_id", table_name="tracked_orders")
    op.drop_table("tracked_orders")
