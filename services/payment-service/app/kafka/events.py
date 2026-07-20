import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.models import Payment, PaymentEvent


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def build_event_message(payment: Payment, event: PaymentEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "occurred_at": _to_utc_iso(event.created_at),
        "service": "payment-service",
        "aggregate_type": "payment",
        "aggregate_id": str(payment.id),
        "payload": event.payload,
        "metadata": {
            "payment_id": str(payment.id),
            "order_id": str(payment.order_id),
            "user_id": str(payment.user_id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency,
        },
    }


def build_custom_event(
    *,
    event_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any],
    payment: Payment,
) -> dict[str, Any]:
    return {
        "event_id": str(event_id),
        "event_type": event_type,
        "occurred_at": _to_utc_iso(occurred_at),
        "service": "payment-service",
        "aggregate_type": "payment",
        "aggregate_id": str(payment.id),
        "payload": payload,
        "metadata": {
            "payment_id": str(payment.id),
            "order_id": str(payment.order_id),
            "user_id": str(payment.user_id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency,
        },
    }
