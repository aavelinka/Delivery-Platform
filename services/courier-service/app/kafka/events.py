import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.models import Courier, CourierAssignment


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def build_courier_event(
    *,
    event_type: str,
    courier: Courier,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": _to_utc_iso(datetime.now(UTC)),
        "service": "courier-service",
        "aggregate_type": "courier",
        "aggregate_id": str(courier.id),
        "payload": payload,
        "metadata": {
            "courier_id": str(courier.id),
            "user_id": str(courier.user_id),
            "availability": courier.availability.value,
            "is_active": courier.is_active,
        },
    }


def build_assignment_event(
    *,
    event_type: str,
    assignment: CourierAssignment,
    courier: Courier,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": _to_utc_iso(datetime.now(UTC)),
        "service": "courier-service",
        "aggregate_type": "assignment",
        "aggregate_id": str(assignment.id),
        "payload": payload,
        "metadata": {
            "assignment_id": str(assignment.id),
            "courier_id": str(courier.id),
            "courier_user_id": str(courier.user_id),
            "order_id": str(assignment.order_id),
            "status": assignment.status.value,
        },
    }
