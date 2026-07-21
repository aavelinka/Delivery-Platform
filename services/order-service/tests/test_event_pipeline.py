import asyncio
import uuid
from decimal import Decimal

import pytest
from platform_common.outbox import OutboxPublisher
from platform_common.tracing import start_trace
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


class FakeKafkaMessage:
    def __init__(self, *, topic: str, value: dict[str, object]) -> None:
        self.topic = topic
        self.value = value
        self.partition = 0
        self.offset = 1


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


def test_outbox_event_includes_trace_metadata(db_session):
    with start_trace() as trace_context:
        _create_order(db_session)

    pending_event = db_session.scalar(select(OutboxEvent))
    assert pending_event is not None

    trace_metadata = pending_event.payload["metadata"]["trace"]
    assert trace_metadata["trace_id"] == trace_context.trace_id
    assert trace_metadata["span_id"] == trace_context.span_id
    assert trace_metadata["traceparent"] == trace_context.traceparent


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
    with start_trace() as upstream_trace:
        trace_metadata = upstream_trace.as_metadata()

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
                    "trace": trace_metadata,
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
                    "trace": trace_metadata,
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

        propagated_events = [
            event
            for event in outbox_events
            if event.payload["event_type"] in {"courier_assigned", "delivery_started"}
        ]
        assert len(propagated_events) == 2
        for event in propagated_events:
            trace = event.payload["metadata"]["trace"]
            assert trace["trace_id"] == upstream_trace.trace_id
            assert trace["parent_span_id"] == upstream_trace.span_id
            assert trace["span_id"] != upstream_trace.span_id


def test_courier_consumer_dead_letters_poison_message(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    old_max_retries = settings.kafka_consumer_max_retries
    old_retry_backoff = settings.kafka_consumer_retry_backoff_seconds
    publisher = RecordingPublisher()
    consumer = CourierEventsConsumer(settings, publisher)
    message = FakeKafkaMessage(
        topic=settings.kafka_couriers_topic,
        value={
            "event_id": str(uuid.uuid4()),
            "event_type": "courier_assigned",
            "aggregate_type": "assignment",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {"order_id": str(uuid.uuid4())},
            "metadata": {},
        },
    )

    async def always_fail(event: dict[str, object], topic: str | None = None) -> None:
        del event, topic
        raise RuntimeError("broken assignment event")

    monkeypatch.setattr(consumer, "_handle_event", always_fail)
    settings.kafka_consumer_max_retries = 0
    settings.kafka_consumer_retry_backoff_seconds = 0

    try:
        should_commit = asyncio.run(consumer._process_message(message))
    finally:
        settings.kafka_consumer_max_retries = old_max_retries
        settings.kafka_consumer_retry_backoff_seconds = old_retry_backoff

    assert should_commit is True
    assert len(publisher.messages) == 1
    topic, dlq_event = publisher.messages[0]
    assert topic == settings.kafka_consumer_dlq_topic
    assert dlq_event["event_type"] == "dead_lettered"
    assert dlq_event["payload"]["source_topic"] == settings.kafka_couriers_topic
    assert dlq_event["payload"]["failed_attempts"] == 1
    assert dlq_event["payload"]["original_event"]["event_id"] == message.value["event_id"]
