import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from platform_common.outbox import add_outbox_event
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Order, OrderEvent, OutboxEvent
from app.domain.enums import ALLOWED_STATUS_TRANSITIONS, OrderStatus
from app.kafka.events import build_event_message
from app.schemas.orders import OrderCancel, OrderCreate, OrderStatusUpdate


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def order_payload(order: Order) -> dict[str, Any]:
    return {
        "order_id": str(order.id),
        "user_id": str(order.user_id),
        "courier_user_id": str(order.courier_id) if order.courier_id else None,
        "pickup_address": order.pickup_address,
        "delivery_address": order.delivery_address,
        "status": order.status.value,
        "total_price": str(order.total_price),
        "comment": order.comment,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
    }


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_order(self, data: OrderCreate) -> tuple[Order, OrderEvent]:
        order = Order(
            user_id=data.user_id,
            pickup_address=data.pickup_address,
            delivery_address=data.delivery_address,
            total_price=data.total_price,
            comment=data.comment,
            status=OrderStatus.CREATED,
        )
        self.db.add(order)
        self.db.flush()

        event = self._add_event(
            order=order,
            event_type="order_created",
            previous_status=None,
            new_status=order.status,
            payload=order_payload(order),
        )
        self._add_outbox_event(order, event)

        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(event)
        return order, event

    def get_order(self, order_id: uuid.UUID) -> Order:
        order = self.db.get(Order, order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return order

    def list_orders(
        self,
        *,
        status_filter: OrderStatus | None,
        user_id: uuid.UUID | None,
        courier_id: uuid.UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Order], int]:
        query: Select[tuple[Order]] = select(Order)
        count_query = select(func.count()).select_from(Order)

        filters = []
        if status_filter is not None:
            filters.append(Order.status == status_filter)
        if user_id is not None:
            filters.append(Order.user_id == user_id)
        if courier_id is not None:
            filters.append(Order.courier_id == courier_id)
        if created_from is not None:
            filters.append(Order.created_at >= created_from)
        if created_to is not None:
            filters.append(Order.created_at <= created_to)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = self.db.scalar(count_query) or 0
        items = self.db.scalars(
            query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(items), total

    def get_admin_summary(self) -> dict[str, int | dict[str, int]]:
        total_orders = self.db.scalar(select(func.count()).select_from(Order)) or 0
        orders_with_courier = (
            self.db.scalar(select(func.count()).select_from(Order).where(Order.courier_id.is_not(None)))
            or 0
        )
        completed_orders = (
            self.db.scalar(
                select(func.count()).select_from(Order).where(Order.status == OrderStatus.DELIVERED)
            )
            or 0
        )
        cancelled_orders = (
            self.db.scalar(
                select(func.count()).select_from(Order).where(Order.status == OrderStatus.CANCELLED)
            )
            or 0
        )
        status_rows = self.db.execute(
            select(Order.status, func.count()).group_by(Order.status)
        ).all()
        orders_by_status = {
            str(status.value if isinstance(status, OrderStatus) else status): count
            for status, count in status_rows
        }
        return {
            "total_orders": total_orders,
            "orders_with_courier": orders_with_courier,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,
            "orders_by_status": orders_by_status,
        }

    def change_status(
        self,
        order_id: uuid.UUID,
        data: OrderStatusUpdate,
    ) -> tuple[Order, OrderEvent]:
        order = self.get_order(order_id)
        previous_status = order.status

        if data.status == previous_status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order already has this status",
            )

        allowed_next_statuses = ALLOWED_STATUS_TRANSITIONS[previous_status]
        if data.status not in allowed_next_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot change order status from {previous_status} to {data.status}",
            )

        if data.status in {OrderStatus.COURIER_ASSIGNED, OrderStatus.IN_DELIVERY}:
            if data.courier_user_id is not None:
                order.courier_id = data.courier_user_id
            if order.courier_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="courier_user_id is required for this status",
                )

        order.status = data.status
        order.updated_at = datetime.now(UTC)

        event_type = self._event_type_for_status(data.status)
        event = self._add_event(
            order=order,
            event_type=event_type,
            previous_status=previous_status,
            new_status=data.status,
            changed_by=data.changed_by,
            payload=order_payload(order),
        )
        self._add_outbox_event(order, event)

        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(event)
        return order, event

    def cancel_order(self, order_id: uuid.UUID, data: OrderCancel) -> tuple[Order, OrderEvent]:
        order = self.get_order(order_id)
        previous_status = order.status

        if OrderStatus.CANCELLED not in ALLOWED_STATUS_TRANSITIONS[previous_status]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel order from {previous_status}",
            )

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now(UTC)
        order.updated_at = order.cancelled_at

        payload = order_payload(order)
        payload["reason"] = data.reason

        event = self._add_event(
            order=order,
            event_type="order_cancelled",
            previous_status=previous_status,
            new_status=OrderStatus.CANCELLED,
            changed_by=data.changed_by,
            payload=payload,
        )
        self._add_outbox_event(order, event)

        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(event)
        return order, event

    def apply_courier_assigned(
        self,
        courier_event: dict[str, Any],
    ) -> tuple[Order, OrderEvent] | None:
        payload = self._event_object(courier_event.get("payload"))
        metadata = self._event_object(courier_event.get("metadata"))

        order_id = self._parse_uuid(payload.get("order_id") or metadata.get("order_id"))
        courier_user_id = self._parse_uuid(
            payload.get("courier_user_id") or metadata.get("courier_user_id")
        )
        if order_id is None or courier_user_id is None:
            return None

        order = self.db.get(Order, order_id)
        if order is None:
            return None
        if order.status == OrderStatus.COURIER_ASSIGNED and order.courier_id == courier_user_id:
            existing_event = self.db.scalar(
                select(OrderEvent)
                .where(OrderEvent.order_id == order.id)
                .where(OrderEvent.event_type == "courier_assigned")
                .order_by(OrderEvent.created_at.desc())
            )
            if existing_event is None:
                return None
            return order, existing_event
        if OrderStatus.COURIER_ASSIGNED not in ALLOWED_STATUS_TRANSITIONS[order.status]:
            return None

        previous_status = order.status
        order.courier_id = courier_user_id
        order.status = OrderStatus.COURIER_ASSIGNED
        order.updated_at = datetime.now(UTC)

        event = self._add_event(
            order=order,
            event_type="courier_assigned",
            previous_status=previous_status,
            new_status=OrderStatus.COURIER_ASSIGNED,
            changed_by="courier-service",
            payload={
                **order_payload(order),
                "source_event_id": courier_event.get("event_id"),
                "source_event_type": courier_event.get("event_type"),
                "assignment_id": payload.get("assignment_id") or metadata.get("assignment_id"),
            },
        )
        self._add_outbox_event(order, event)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(event)
        return order, event

    def apply_assignment_status_changed(
        self,
        courier_event: dict[str, Any],
    ) -> tuple[Order, OrderEvent] | None:
        payload, metadata = self._event_payload_and_metadata(courier_event)
        order_id = self._parse_uuid(payload.get("order_id") or metadata.get("order_id"))
        courier_user_id = self._parse_uuid(
            payload.get("courier_user_id") or metadata.get("courier_user_id")
        )
        assignment_status = str(payload.get("status") or metadata.get("status") or "")
        if order_id is None or courier_user_id is None:
            return None

        target_status = self._order_status_for_assignment_status(assignment_status)
        if target_status is None:
            return None

        order = self.db.get(Order, order_id)
        if order is None or order.courier_id != courier_user_id:
            return None
        if order.status == target_status:
            existing_event = self.db.scalar(
                select(OrderEvent)
                .where(OrderEvent.order_id == order.id)
                .where(OrderEvent.event_type == self._event_type_for_status(target_status))
                .order_by(OrderEvent.created_at.desc())
            )
            if existing_event is None:
                return None
            return order, existing_event
        if target_status not in ALLOWED_STATUS_TRANSITIONS[order.status]:
            return None

        previous_status = order.status
        order.status = target_status
        if target_status == OrderStatus.WAITING_FOR_COURIER:
            order.courier_id = None
        order.updated_at = datetime.now(UTC)

        event = self._add_event(
            order=order,
            event_type=self._event_type_for_status(target_status),
            previous_status=previous_status,
            new_status=target_status,
            changed_by="courier-service",
            payload={
                **order_payload(order),
                "source_event_id": courier_event.get("event_id"),
                "source_event_type": courier_event.get("event_type"),
                "assignment_id": payload.get("assignment_id") or metadata.get("assignment_id"),
                "assignment_status": assignment_status,
            },
        )
        self._add_outbox_event(order, event)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(event)
        return order, event

    def list_events(self, order_id: uuid.UUID) -> list[OrderEvent]:
        self.get_order(order_id)
        return list(
            self.db.scalars(
                select(OrderEvent)
                .where(OrderEvent.order_id == order_id)
                .order_by(OrderEvent.created_at.asc())
            ).all()
        )

    def _add_event(
        self,
        *,
        order: Order,
        event_type: str,
        previous_status: OrderStatus | None,
        new_status: OrderStatus | None,
        payload: dict[str, Any],
        changed_by: str | None = None,
    ) -> OrderEvent:
        event = OrderEvent(
            order_id=order.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=changed_by,
            payload=_json_safe(payload),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def _add_outbox_event(self, order: Order, event: OrderEvent) -> None:
        settings = get_settings()
        add_outbox_event(
            self.db,
            OutboxEvent,
            topic=settings.kafka_orders_topic,
            payload=build_event_message(order, event),
        )

    @staticmethod
    def _event_type_for_status(status_value: OrderStatus) -> str:
        if status_value == OrderStatus.COURIER_ASSIGNED:
            return "courier_assigned"
        if status_value == OrderStatus.IN_DELIVERY:
            return "delivery_started"
        if status_value == OrderStatus.DELIVERED:
            return "delivery_completed"
        return "order_status_changed"

    @staticmethod
    def _order_status_for_assignment_status(assignment_status: str) -> OrderStatus | None:
        if assignment_status in {"accepted", "picked_up"}:
            return OrderStatus.IN_DELIVERY
        if assignment_status == "delivered":
            return OrderStatus.DELIVERED
        if assignment_status == "cancelled":
            return OrderStatus.WAITING_FOR_COURIER
        return None

    @staticmethod
    def _event_payload_and_metadata(
        event: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            OrderService._event_object(event.get("payload")),
            OrderService._event_object(event.get("metadata")),
        )

    @staticmethod
    def _event_object(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items()}

    @staticmethod
    def _parse_uuid(value: Any) -> uuid.UUID | None:
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None
