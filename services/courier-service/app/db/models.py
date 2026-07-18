import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import AssignmentStatus, CourierAvailability


def utc_now() -> datetime:
    return datetime.now(UTC)


class Courier(Base):
    __tablename__ = "couriers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    vehicle_type: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(128))
    availability: Mapped[CourierAvailability] = mapped_column(
        Enum(
            CourierAvailability,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
            length=32,
        ),
        index=True,
        nullable=False,
        default=CourierAvailability.OFFLINE,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    assignments: Mapped[list["CourierAssignment"]] = relationship(
        back_populates="courier",
        cascade="all, delete-orphan",
        order_by="CourierAssignment.assigned_at",
    )


class CourierAssignment(Base):
    __tablename__ = "courier_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    courier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("couriers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(
            AssignmentStatus,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
            length=32,
        ),
        index=True,
        nullable=False,
        default=AssignmentStatus.ASSIGNED,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    courier: Mapped[Courier] = relationship(back_populates="assignments")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_couriers_availability_created_at", Courier.availability, Courier.created_at)
Index("ix_assignments_courier_status", CourierAssignment.courier_id, CourierAssignment.status)
Index("ix_courier_outbox_status_created_at", OutboxEvent.status, OutboxEvent.created_at)
