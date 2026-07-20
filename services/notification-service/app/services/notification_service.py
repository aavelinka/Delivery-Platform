import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.domain.enums import NotificationChannel, NotificationStatus
from app.schemas.notifications import NotificationCreate


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_notification(self, data: NotificationCreate) -> Notification:
        notification = Notification(
            user_id=data.user_id,
            channel=data.channel,
            status=NotificationStatus.CREATED,
            title=data.title,
            message=data.message,
            payload=data.payload,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def create_from_event(self, event: dict[str, Any]) -> Notification | None:
        source_event_id = str(event.get("event_id")) if event.get("event_id") else None
        if source_event_id is not None:
            existing = self.db.scalar(
                select(Notification).where(Notification.source_event_id == source_event_id)
            )
            if existing is not None:
                return existing

        notification_data = self._notification_from_event(event)
        if notification_data is None:
            return None

        notification = Notification(**notification_data)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def get_notification(self, notification_id: uuid.UUID) -> Notification:
        notification = self.db.get(Notification, notification_id)
        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )
        return notification

    def list_user_notifications(
        self,
        *,
        user_id: uuid.UUID,
        unread_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        query: Select[tuple[Notification]] = select(Notification).where(
            Notification.user_id == user_id
        )
        count_query = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id
        )

        if unread_only:
            query = query.where(Notification.read_at.is_(None))
            count_query = count_query.where(Notification.read_at.is_(None))

        total = self.db.scalar(count_query) or 0
        items = self.db.scalars(
            query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def get_admin_summary(self) -> dict[str, int | dict[str, int]]:
        total_notifications = self.db.scalar(select(func.count()).select_from(Notification)) or 0
        read_notifications = (
            self.db.scalar(select(func.count()).select_from(Notification).where(Notification.read_at.is_not(None)))
            or 0
        )
        status_rows = self.db.execute(
            select(Notification.status, func.count()).group_by(Notification.status)
        ).all()
        channel_rows = self.db.execute(
            select(Notification.channel, func.count()).group_by(Notification.channel)
        ).all()
        notifications_by_status = {
            str(status.value if isinstance(status, NotificationStatus) else status): count
            for status, count in status_rows
        }
        notifications_by_channel = {
            str(channel.value if isinstance(channel, NotificationChannel) else channel): count
            for channel, count in channel_rows
        }
        return {
            "total_notifications": total_notifications,
            "read_notifications": read_notifications,
            "unread_notifications": total_notifications - read_notifications,
            "notifications_by_status": notifications_by_status,
            "notifications_by_channel": notifications_by_channel,
        }

    def mark_as_read(self, notification_id: uuid.UUID) -> Notification:
        notification = self.get_notification(notification_id)
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            notification.status = NotificationStatus.READ
            self.db.commit()
            self.db.refresh(notification)
        return notification

    def _notification_from_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(event.get("event_type") or "")
        payload = self._event_object(event.get("payload"))
        metadata = self._event_object(event.get("metadata"))

        user_id = self._recipient_user_id(payload, metadata)
        title, message = self._message_for_event(event_type, payload, metadata)
        if user_id is None or title is None or message is None:
            return None

        return {
            "user_id": user_id,
            "channel": NotificationChannel.IN_APP,
            "status": NotificationStatus.CREATED,
            "title": title,
            "message": message,
            "source_event_type": event_type,
            "source_event_id": str(event.get("event_id")) if event.get("event_id") else None,
            "aggregate_type": (
                str(event.get("aggregate_type")) if event.get("aggregate_type") else None
            ),
            "aggregate_id": str(event.get("aggregate_id")) if event.get("aggregate_id") else None,
            "payload": event,
        }

    @staticmethod
    def _message_for_event(
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        order_id = payload.get("order_id") or metadata.get("order_id")
        courier_id = (
            payload.get("courier_user_id")
            or metadata.get("courier_user_id")
            or payload.get("courier_id")
            or metadata.get("courier_id")
        )

        messages = {
            "order_created": (
                "Order created",
                f"Order {order_id} was created and is waiting for processing.",
            ),
            "order_cancelled": (
                "Order cancelled",
                f"Order {order_id} was cancelled.",
            ),
            "order_status_changed": (
                "Order status changed",
                f"Order {order_id} status was changed to {metadata.get('status')}.",
            ),
            "delivery_started": (
                "Delivery started",
                f"Courier started delivering order {order_id}.",
            ),
            "delivery_completed": (
                "Delivery completed",
                f"Order {order_id} was delivered.",
            ),
            "courier_assigned": (
                "Courier assigned",
                f"Courier {courier_id} was assigned to order {order_id}.",
            ),
            "courier_availability_changed": (
                "Courier availability changed",
                f"Courier {courier_id} availability changed to {metadata.get('availability')}.",
            ),
            "assignment_status_changed": (
                "Assignment status changed",
                f"Courier assignment for order {order_id} changed to {metadata.get('status')}.",
            ),
        }
        return messages.get(event_type, (None, None))

    @staticmethod
    def _event_object(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items()}

    @staticmethod
    def _recipient_user_id(
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> uuid.UUID | None:
        return _parse_uuid(
            payload.get("user_id")
            or metadata.get("user_id")
            or payload.get("courier_user_id")
            or metadata.get("courier_user_id")
        )
