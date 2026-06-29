from datetime import UTC
from typing import Any

from app.db.models import CourierLocation


def build_location_event(location: CourierLocation) -> dict[str, Any]:
    recorded_at = location.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)

    return {
        "event_id": str(location.id),
        "event_type": "courier_location_updated",
        "occurred_at": recorded_at.astimezone(UTC).isoformat(),
        "service": "tracking-service",
        "aggregate_type": "courier",
        "aggregate_id": str(location.courier_user_id),
        "payload": {
            "location_id": str(location.id),
            "courier_user_id": str(location.courier_user_id),
            "user_id": str(location.user_id) if location.user_id else None,
            "order_id": str(location.order_id) if location.order_id else None,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "accuracy_meters": location.accuracy_meters,
            "recorded_at": recorded_at.astimezone(UTC).isoformat(),
            "payload": location.payload,
        },
        "metadata": {
            "courier_user_id": str(location.courier_user_id),
            "user_id": str(location.user_id) if location.user_id else None,
            "order_id": str(location.order_id) if location.order_id else None,
        },
    }
