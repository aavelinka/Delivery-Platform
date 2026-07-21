import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Courier, CourierAssignment, OutboxEvent
from app.db.session import SessionLocal
from app.domain.enums import CourierAvailability
from app.kafka.consumer import OrderEventsConsumer
from app.schemas.couriers import CourierAvailabilityUpdate, CourierCreate
from app.services.courier_service import CourierService


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, object]]] = []

    async def publish(self, topic: str, message: dict[str, object]) -> None:
        self.messages.append((topic, message))


class FakeKafkaMessage:
    def __init__(self, *, topic: str, value: dict[str, object]) -> None:
        self.topic = topic
        self.value = value
        self.partition = 0
        self.offset = 1


def _create_online_courier(db_session) -> Courier:
    service = CourierService(db_session)
    courier = service.create_courier(
        CourierCreate(
            user_id=uuid.uuid4(),
            full_name="Alex Smith",
            phone="+375291112233",
            vehicle_type="bike",
            city="Minsk",
        )
    )
    return service.change_availability(
        courier.id,
        CourierAvailabilityUpdate(availability=CourierAvailability.ONLINE),
    )


def test_order_consumer_auto_assigns_event_once(db_session):
    courier = _create_online_courier(db_session)
    order_id = uuid.uuid4()
    event_id = uuid.uuid4()
    consumer = OrderEventsConsumer(get_settings())
    order_event = {
        "event_id": str(event_id),
        "event_type": "order_created",
        "aggregate_type": "order",
        "aggregate_id": str(order_id),
        "payload": {
            "order_id": str(order_id),
            "user_id": str(uuid.uuid4()),
            "delivery_city": "Minsk",
        },
        "metadata": {
            "order_id": str(order_id),
            "status": "created",
        },
    }

    asyncio.run(consumer._handle_event(order_event))
    asyncio.run(consumer._handle_event(order_event))

    with SessionLocal() as verify_db:
        assignments = list(
            verify_db.scalars(
                select(CourierAssignment).where(CourierAssignment.order_id == order_id)
            ).all()
        )
        assert len(assignments) == 1
        assert assignments[0].courier_id == courier.id

        refreshed_courier = verify_db.get(Courier, courier.id)
        assert refreshed_courier is not None
        assert refreshed_courier.availability == CourierAvailability.BUSY

        assignment_events = [
            event
            for event in verify_db.scalars(
                select(OutboxEvent).order_by(OutboxEvent.created_at)
            ).all()
            if event.payload["event_type"] == "courier_assigned"
            and event.payload["metadata"]["order_id"] == str(order_id)
        ]
        assert len(assignment_events) == 1


def test_order_consumer_dead_letters_poison_message(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    old_max_retries = settings.kafka_consumer_max_retries
    old_retry_backoff = settings.kafka_consumer_retry_backoff_seconds
    publisher = RecordingPublisher()
    consumer = OrderEventsConsumer(settings, publisher)
    message = FakeKafkaMessage(
        topic=settings.kafka_orders_topic,
        value={
            "event_id": str(uuid.uuid4()),
            "event_type": "order_created",
            "aggregate_type": "order",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {"order_id": str(uuid.uuid4())},
            "metadata": {},
        },
    )

    async def always_fail(event: dict[str, object], topic: str | None = None) -> None:
        del event, topic
        raise RuntimeError("broken order event")

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
    assert dlq_event["payload"]["source_topic"] == settings.kafka_orders_topic
    assert dlq_event["payload"]["failed_attempts"] == 1
    assert dlq_event["payload"]["original_event"]["event_id"] == message.value["event_id"]
