import asyncio
import uuid
from decimal import Decimal

from platform_common.outbox import OutboxPublisher
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Order, OutboxEvent
from app.db.session import SessionLocal
from app.domain.enums import OrderStatus
from app.kafka.consumer import CourierEventsConsumer
from app.schemas.orders import OrderCreate
from app.services.order_service import OrderService


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, object]]] = []

    async def publish(self, topic: str, message: dict[str, object]) -> None:
        self.messages.append((topic, message))


class FlakyPublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish(self, topic: str, message: dict[str, object]) -> None:
        del topic, message
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")


def _create_order(db_session) -> Order:
    service = OrderService(db_session)
    order, _event = service.create_order(
        OrderCreate(
            user_id=uuid.uuid4(),
            pickup_address="Warehouse A",
            delivery_address="Main street 12",
            total_price=Decimal("149.90"),
        )
    )
    return order


def test_outbox_publisher_marks_order_event_as_published(db_session):
    _create_order(db_session)
    pending_event = db_session.scalar(select(OutboxEvent))
    assert pending_event is not None

    publisher = RecordingPublisher()
    outbox_publisher = OutboxPublisher(
        session_factory=SessionLocal,
        event_model=OutboxEvent,
        publisher=publisher,
    )

    asyncio.run(outbox_publisher._publish_batch())

    with SessionLocal() as verify_db:
        published_event = verify_db.scalar(select(OutboxEvent))
        assert published_event is not None
        assert published_event.status == "published"
        assert published_event.published_at is not None
        assert published_event.last_error is None
        assert publisher.messages == [(published_event.topic, published_event.payload)]


def test_outbox_publisher_retries_failed_order_event(db_session):
    _create_order(db_session)

    publisher = FlakyPublisher()
    outbox_publisher = OutboxPublisher(
        session_factory=SessionLocal,
        event_model=OutboxEvent,
        publisher=publisher,
    )

    asyncio.run(outbox_publisher._publish_batch())

    with SessionLocal() as verify_db:
        failed_event = verify_db.scalar(select(OutboxEvent))
        assert failed_event is not None
        assert failed_event.status == "pending"
        assert failed_event.attempts == 1
        assert failed_event.last_error == "temporary failure"
        assert failed_event.published_at is None

    asyncio.run(outbox_publisher._publish_batch())

    with SessionLocal() as verify_db:
        published_event = verify_db.scalar(select(OutboxEvent))
        assert published_event is not None
        assert published_event.status == "published"
        assert published_event.attempts == 1
        assert published_event.last_error is None
        assert published_event.published_at is not None
        assert publisher.calls == 2


def test_courier_consumer_applies_assignment_events(db_session):
    order = _create_order(db_session)
    courier_user_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    consumer = CourierEventsConsumer(get_settings())

    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "courier_assigned",
                "aggregate_type": "assignment",
                "aggregate_id": str(assignment_id),
                "payload": {
                    "assignment_id": str(assignment_id),
                    "order_id": str(order.id),
                    "courier_user_id": str(courier_user_id),
                },
                "metadata": {
                    "assignment_id": str(assignment_id),
                    "order_id": str(order.id),
                    "courier_user_id": str(courier_user_id),
                    "status": "assigned",
                },
            }
        )
    )
    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "assignment_status_changed",
                "aggregate_type": "assignment",
                "aggregate_id": str(assignment_id),
                "payload": {
                    "assignment_id": str(assignment_id),
                    "order_id": str(order.id),
                    "courier_user_id": str(courier_user_id),
                    "status": "picked_up",
                },
                "metadata": {
                    "assignment_id": str(assignment_id),
                    "order_id": str(order.id),
                    "courier_user_id": str(courier_user_id),
                    "status": "picked_up",
                },
            }
        )
    )

    with SessionLocal() as verify_db:
        updated_order = verify_db.get(Order, order.id)
        assert updated_order is not None
        assert updated_order.courier_id == courier_user_id
        assert updated_order.status == OrderStatus.IN_DELIVERY

        outbox_events = list(
            verify_db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
        )
        event_types = [event.payload["event_type"] for event in outbox_events]
        assert "courier_assigned" in event_types
        assert "delivery_started" in event_types
