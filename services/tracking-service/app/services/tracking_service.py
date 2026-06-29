import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from platform_common.outbox import add_outbox_event
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import CourierLocation, OutboxEvent, TrackedOrder
from app.kafka.events import build_location_event
from app.schemas.tracking import LocationCreate


class TrackingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_location(self, data: LocationCreate) -> CourierLocation:
        tracked_order = self.get_tracked_order(data.order_id)
        user_id = None
        if data.order_id is not None and tracked_order is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order tracking data is not initialized",
            )
        if tracked_order is not None:
            if tracked_order.courier_user_id not in {None, data.courier_user_id}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Order is tracked by another courier",
                )
            user_id = tracked_order.user_id

        location = CourierLocation(
            courier_user_id=data.courier_user_id,
            user_id=user_id,
            order_id=data.order_id,
            latitude=data.latitude,
            longitude=data.longitude,
            accuracy_meters=data.accuracy_meters,
            recorded_at=data.recorded_at or datetime.now(UTC),
            payload=data.payload,
        )
        self.db.add(location)
        self.db.flush()
        self._add_location_outbox_event(location)
        self.db.commit()
        self.db.refresh(location)
        return location

    def upsert_tracked_order(
        self,
        *,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        courier_user_id: uuid.UUID | None = None,
    ) -> TrackedOrder:
        tracked_order = self.db.get(TrackedOrder, order_id)
        if tracked_order is None:
            tracked_order = TrackedOrder(
                order_id=order_id,
                user_id=user_id,
                courier_user_id=courier_user_id,
            )
            self.db.add(tracked_order)
        else:
            tracked_order.user_id = user_id
            if courier_user_id is not None:
                tracked_order.courier_user_id = courier_user_id
            tracked_order.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(tracked_order)
        return tracked_order

    def apply_order_event(self, event: dict[str, object]) -> TrackedOrder | None:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        order_id = self._parse_uuid(payload.get("order_id") or metadata.get("order_id"))
        user_id = self._parse_uuid(payload.get("user_id") or metadata.get("user_id"))
        courier_user_id = self._parse_uuid(
            payload.get("courier_user_id") or metadata.get("courier_user_id")
        )
        if order_id is None or user_id is None:
            return None
        return self.upsert_tracked_order(
            order_id=order_id,
            user_id=user_id,
            courier_user_id=courier_user_id,
        )

    def get_current_for_order(self, order_id: uuid.UUID) -> CourierLocation:
        location = self.db.scalar(self._base_order_query(order_id).limit(1))
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        return location

    def list_order_history(
        self,
        *,
        order_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[CourierLocation], CourierLocation]:
        current_location = self.get_current_for_order(order_id)
        return list(
            self.db.scalars(
                self._base_order_query(order_id).limit(limit).offset(offset)
            ).all()
        ), current_location

    def get_current_for_courier(self, courier_user_id: uuid.UUID) -> CourierLocation:
        location = self.db.scalar(
            select(CourierLocation)
            .where(CourierLocation.courier_user_id == courier_user_id)
            .order_by(CourierLocation.recorded_at.desc())
            .limit(1)
        )
        if location is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
        return location

    def get_tracked_order(self, order_id: uuid.UUID | None) -> TrackedOrder | None:
        if order_id is None:
            return None
        return self.db.get(TrackedOrder, order_id)

    def _add_location_outbox_event(self, location: CourierLocation) -> None:
        settings = get_settings()
        add_outbox_event(
            self.db,
            OutboxEvent,
            topic=settings.kafka_topic,
            payload=build_location_event(location),
        )

    @staticmethod
    def _base_order_query(order_id: uuid.UUID) -> Select[tuple[CourierLocation]]:
        return (
            select(CourierLocation)
            .where(CourierLocation.order_id == order_id)
            .order_by(CourierLocation.recorded_at.desc())
        )

    @staticmethod
    def _parse_uuid(value: object) -> uuid.UUID | None:
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None
