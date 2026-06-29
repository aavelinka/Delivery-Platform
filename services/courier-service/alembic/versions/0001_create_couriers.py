"""create couriers tables

Revision ID: 0001_create_couriers
Revises:
Create Date: 2026-06-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_create_couriers"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    availability = sa.Enum(
        "online",
        "offline",
        "busy",
        name="courieravailability",
        native_enum=False,
        length=32,
    )
    assignment_status = sa.Enum(
        "assigned",
        "accepted",
        "picked_up",
        "delivered",
        "cancelled",
        name="assignmentstatus",
        native_enum=False,
        length=32,
    )
    availability.create(op.get_bind(), checkfirst=True)
    assignment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "couriers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("vehicle_type", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("availability", availability, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_couriers_user_id", "couriers", ["user_id"])
    op.create_index("ix_couriers_availability", "couriers", ["availability"])
    op.create_index(
        "ix_couriers_availability_created_at",
        "couriers",
        ["availability", "created_at"],
    )

    op.create_table(
        "courier_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "courier_id",
            sa.Uuid(),
            sa.ForeignKey("couriers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", assignment_status, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_courier_assignments_courier_id", "courier_assignments", ["courier_id"])
    op.create_index("ix_courier_assignments_order_id", "courier_assignments", ["order_id"])
    op.create_index("ix_courier_assignments_status", "courier_assignments", ["status"])
    op.create_index(
        "ix_assignments_courier_status",
        "courier_assignments",
        ["courier_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_assignments_courier_status", table_name="courier_assignments")
    op.drop_index("ix_courier_assignments_status", table_name="courier_assignments")
    op.drop_index("ix_courier_assignments_order_id", table_name="courier_assignments")
    op.drop_index("ix_courier_assignments_courier_id", table_name="courier_assignments")
    op.drop_table("courier_assignments")

    op.drop_index("ix_couriers_availability_created_at", table_name="couriers")
    op.drop_index("ix_couriers_availability", table_name="couriers")
    op.drop_index("ix_couriers_user_id", table_name="couriers")
    op.drop_table("couriers")
