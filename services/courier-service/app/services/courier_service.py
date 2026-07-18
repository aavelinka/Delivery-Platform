import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from platform_common.outbox import add_outbox_event
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Courier, CourierAssignment, OutboxEvent
from app.domain.enums import ALLOWED_ASSIGNMENT_TRANSITIONS, AssignmentStatus, CourierAvailability
from app.kafka.events import build_assignment_event, build_courier_event
from app.schemas.couriers import (
    AssignmentCreate,
    AssignmentStatusUpdate,
    CourierAvailabilityUpdate,
    CourierCreate,
    CourierUpdate,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def courier_payload(courier: Courier) -> dict[str, Any]:
    return {
        "courier_id": str(courier.id),
        "user_id": str(courier.user_id),
        "full_name": courier.full_name,
        "phone": courier.phone,
        "vehicle_type": courier.vehicle_type,
        "city": courier.city,
        "availability": courier.availability.value,
        "is_active": courier.is_active,
        "notes": courier.notes,
        "created_at": courier.created_at.isoformat(),
        "updated_at": courier.updated_at.isoformat(),
    }


def assignment_payload(
    assignment: CourierAssignment,
    courier: Courier | None = None,
) -> dict[str, Any]:
    return {
        "assignment_id": str(assignment.id),
        "courier_id": str(assignment.courier_id),
        "courier_user_id": str(courier.user_id) if courier is not None else None,
        "order_id": str(assignment.order_id),
        "status": assignment.status.value,
        "assigned_at": assignment.assigned_at.isoformat(),
        "accepted_at": assignment.accepted_at.isoformat() if assignment.accepted_at else None,
        "picked_up_at": assignment.picked_up_at.isoformat() if assignment.picked_up_at else None,
        "delivered_at": assignment.delivered_at.isoformat() if assignment.delivered_at else None,
        "cancelled_at": assignment.cancelled_at.isoformat() if assignment.cancelled_at else None,
        "payload": assignment.payload,
    }


class CourierService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_courier(self, data: CourierCreate) -> Courier:
        courier = Courier(
            user_id=data.user_id,
            full_name=data.full_name,
            phone=data.phone,
            vehicle_type=data.vehicle_type,
            city=data.city,
            notes=data.notes,
            availability=CourierAvailability.OFFLINE,
            is_active=True,
        )
        self.db.add(courier)
        self.db.flush()
        self._add_courier_outbox_event("courier_created", courier, courier_payload(courier))
        self.db.commit()
        self.db.refresh(courier)
        return courier

    def get_courier(self, courier_id: uuid.UUID) -> Courier:
        courier = self.db.get(Courier, courier_id)
        if courier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
        return courier

    def update_courier(self, courier_id: uuid.UUID, data: CourierUpdate) -> Courier:
        courier = self.get_courier(courier_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(courier, field, value)
        courier.updated_at = datetime.now(UTC)
        self._add_courier_outbox_event("courier_updated", courier, courier_payload(courier))
        self.db.commit()
        self.db.refresh(courier)
        return courier

    def change_availability(
        self, courier_id: uuid.UUID, data: CourierAvailabilityUpdate
    ) -> Courier:
        courier = self.get_courier(courier_id)
        if not courier.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Courier is inactive")
        courier.availability = data.availability
        courier.updated_at = datetime.now(UTC)
        self._add_courier_outbox_event(
            "courier_availability_changed",
            courier,
            {
                "courier_id": str(courier.id),
                "courier_user_id": str(courier.user_id),
                "availability": courier.availability.value,
                "changed_by": data.changed_by,
            },
        )
        self.db.commit()
        self.db.refresh(courier)
        return courier

    def list_available_couriers(
        self, *, city: str | None, limit: int, offset: int
    ) -> tuple[list[Courier], int]:
        query: Select[tuple[Courier]] = select(Courier).where(
            Courier.is_active.is_(True),
            Courier.availability == CourierAvailability.ONLINE,
        )
        count_query = select(func.count()).select_from(Courier).where(
            Courier.is_active.is_(True),
            Courier.availability == CourierAvailability.ONLINE,
        )
        if city is not None:
            query = query.where(Courier.city == city)
            count_query = count_query.where(Courier.city == city)

        total = self.db.scalar(count_query) or 0
        items = self.db.scalars(
            query.order_by(Courier.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def assign_courier(self, data: AssignmentCreate) -> CourierAssignment:
        courier = self.get_courier(data.courier_id)
        if not courier.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Courier is inactive")
        if courier.availability != CourierAvailability.ONLINE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Courier is not available",
            )

        existing_assignment = self.db.scalar(
            select(CourierAssignment).where(
                CourierAssignment.order_id == data.order_id,
                CourierAssignment.status != AssignmentStatus.CANCELLED,
            )
        )
        if existing_assignment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order already has an active assignment",
            )

        assignment = CourierAssignment(
            courier_id=courier.id,
            order_id=data.order_id,
            status=AssignmentStatus.ASSIGNED,
            payload=_json_safe(data.payload),
        )
        courier.availability = CourierAvailability.BUSY
        courier.updated_at = datetime.now(UTC)
        self.db.add(assignment)
        self.db.flush()
        self._add_assignment_outbox_event(
            "courier_assigned",
            assignment,
            courier,
            assignment_payload(assignment, courier),
        )
        self.db.commit()
        self.db.refresh(assignment)
        self.db.refresh(courier)
        return assignment

    def get_assignment(self, assignment_id: uuid.UUID) -> CourierAssignment:
        assignment = self.db.get(CourierAssignment, assignment_id)
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )
        return assignment

    def auto_assign_order(self, order_event: dict[str, Any]) -> CourierAssignment | None:
        payload = self._event_object(order_event.get("payload"))
        order_id_value = payload.get("order_id") or order_event.get("aggregate_id")
        order_id = self._parse_uuid(order_id_value)
        if order_id is None:
            return None

        existing_assignment = self.db.scalar(
            select(CourierAssignment).where(
                CourierAssignment.order_id == order_id,
                CourierAssignment.status != AssignmentStatus.CANCELLED,
            )
        )
        if existing_assignment is not None:
            return existing_assignment

        city = payload.get("city") or payload.get("delivery_city")
        courier = self._find_available_courier(city=city if isinstance(city, str) else None)
        if courier is None:
            return None

        assignment = CourierAssignment(
            courier_id=courier.id,
            order_id=order_id,
            status=AssignmentStatus.ASSIGNED,
            payload=_json_safe(
                {
                    "source_event_id": order_event.get("event_id"),
                    "source_event_type": order_event.get("event_type"),
                    "order": payload,
                }
            ),
        )
        courier.availability = CourierAvailability.BUSY
        courier.updated_at = datetime.now(UTC)
        self.db.add(assignment)
        self.db.flush()
        self._add_assignment_outbox_event(
            "courier_assigned",
            assignment,
            courier,
            assignment_payload(assignment, courier),
        )
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def update_assignment_status(
        self, assignment_id: uuid.UUID, data: AssignmentStatusUpdate
    ) -> CourierAssignment:
        assignment = self.get_assignment(assignment_id)
        previous_status = assignment.status
        if data.status == previous_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assignment already has this status",
            )

        allowed_next_statuses = ALLOWED_ASSIGNMENT_TRANSITIONS[previous_status]
        if data.status not in allowed_next_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot change assignment status from {previous_status} to {data.status}",
            )

        now = datetime.now(UTC)
        courier = self.get_courier(assignment.courier_id)
        assignment.status = data.status
        if data.status == AssignmentStatus.ACCEPTED:
            assignment.accepted_at = now
        elif data.status == AssignmentStatus.PICKED_UP:
            assignment.picked_up_at = now
        elif data.status == AssignmentStatus.DELIVERED:
            assignment.delivered_at = now
            courier.availability = CourierAvailability.ONLINE
            courier.updated_at = now
        elif data.status == AssignmentStatus.CANCELLED:
            assignment.cancelled_at = now
            courier.availability = CourierAvailability.ONLINE
            courier.updated_at = now

        self._add_assignment_outbox_event(
            "assignment_status_changed",
            assignment,
            courier,
            {
                **assignment_payload(assignment, courier),
                "changed_by": data.changed_by,
            },
        )
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def list_assignments(
        self,
        *,
        courier_id: uuid.UUID | None,
        order_id: uuid.UUID | None,
        status_filter: AssignmentStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[CourierAssignment], int]:
        query: Select[tuple[CourierAssignment]] = select(CourierAssignment)
        count_query = select(func.count()).select_from(CourierAssignment)

        filters = []
        if courier_id is not None:
            filters.append(CourierAssignment.courier_id == courier_id)
        if order_id is not None:
            filters.append(CourierAssignment.order_id == order_id)
        if status_filter is not None:
            filters.append(CourierAssignment.status == status_filter)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = self.db.scalar(count_query) or 0
        items = self.db.scalars(
            query.order_by(CourierAssignment.assigned_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def _find_available_courier(self, city: str | None) -> Courier | None:
        base_query = select(Courier).where(
            Courier.is_active.is_(True),
            Courier.availability == CourierAvailability.ONLINE,
        )
        if city is not None:
            city_match = self.db.scalar(
                base_query.where(Courier.city == city).order_by(Courier.created_at.asc())
            )
            if city_match is not None:
                return city_match
        return self.db.scalar(base_query.order_by(Courier.created_at.asc()))

    def _add_courier_outbox_event(
        self,
        event_type: str,
        courier: Courier,
        payload: dict[str, Any],
    ) -> None:
        settings = get_settings()
        add_outbox_event(
            self.db,
            OutboxEvent,
            topic=settings.kafka_couriers_topic,
            payload=build_courier_event(
                event_type=event_type,
                courier=courier,
                payload=payload,
            ),
        )

    def _add_assignment_outbox_event(
        self,
        event_type: str,
        assignment: CourierAssignment,
        courier: Courier,
        payload: dict[str, Any],
    ) -> None:
        settings = get_settings()
        add_outbox_event(
            self.db,
            OutboxEvent,
            topic=settings.kafka_couriers_topic,
            payload=build_assignment_event(
                event_type=event_type,
                assignment=assignment,
                courier=courier,
                payload=payload,
            ),
        )

    @staticmethod
    def _parse_uuid(value: Any) -> uuid.UUID | None:
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _event_object(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items()}
