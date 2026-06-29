import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.models import Order, OrderEvent


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def build_event_message(order: Order, event: OrderEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "occurred_at": _to_utc_iso(event.created_at),
        "service": "order-service",
        "aggregate_type": "order",
        "aggregate_id": str(order.id),
        "payload": event.payload,
        "metadata": {
            "order_id": str(order.id),
            "user_id": str(order.user_id),
            "courier_user_id": str(order.courier_id) if order.courier_id else None,
            "status": order.status.value,
        },
    }


def build_custom_event(
    *,
    event_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any],
    order: Order,
) -> dict[str, Any]:
    return {
        "event_id": str(event_id),
        "event_type": event_type,
        "occurred_at": _to_utc_iso(occurred_at),
        "service": "order-service",
        "aggregate_type": "order",
        "aggregate_id": str(order.id),
        "payload": payload,
        "metadata": {
            "order_id": str(order.id),
            "user_id": str(order.user_id),
            "courier_user_id": str(order.courier_id) if order.courier_id else None,
            "status": order.status.value,
        },
    }
