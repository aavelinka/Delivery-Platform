import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import NotificationChannel, NotificationStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
            length=32,
        ),
        nullable=False,
        default=NotificationChannel.IN_APP,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
            length=32,
        ),
        index=True,
        nullable=False,
        default=NotificationStatus.CREATED,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_type: Mapped[str | None] = mapped_column(String(128), index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str | None] = mapped_column(String(64))
    aggregate_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_notifications_user_created_at", Notification.user_id, Notification.created_at)
Index("ix_notifications_status_created_at", Notification.status, Notification.created_at)
