import asyncio
import uuid

import pytest

from app.core.config import get_settings
from app.db.models import TrackedOrder
from app.db.session import SessionLocal
from app.kafka.consumer import OrderEventsConsumer


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


def test_order_consumer_upserts_and_enriches_tracked_order():
    order_id = uuid.uuid4()
    user_id = uuid.uuid4()
    courier_user_id = uuid.uuid4()
    consumer = OrderEventsConsumer(get_settings())

    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "order_created",
                "aggregate_type": "order",
                "aggregate_id": str(order_id),
                "payload": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                },
                "metadata": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "status": "created",
                },
            }
        )
    )
    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "courier_assigned",
                "aggregate_type": "order",
                "aggregate_id": str(order_id),
                "payload": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": str(courier_user_id),
                },
                "metadata": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": str(courier_user_id),
                    "status": "courier_assigned",
                },
            }
        )
    )

    with SessionLocal() as verify_db:
        tracked_order = verify_db.get(TrackedOrder, order_id)
        assert tracked_order is not None
        assert tracked_order.user_id == user_id
        assert tracked_order.courier_user_id == courier_user_id


def test_order_consumer_clears_courier_when_order_returns_to_queue():
    order_id = uuid.uuid4()
    user_id = uuid.uuid4()
    courier_user_id = uuid.uuid4()
    consumer = OrderEventsConsumer(get_settings())

    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "courier_assigned",
                "aggregate_type": "order",
                "aggregate_id": str(order_id),
                "payload": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": str(courier_user_id),
                },
                "metadata": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": str(courier_user_id),
                    "status": "courier_assigned",
                },
            }
        )
    )
    asyncio.run(
        consumer._handle_event(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "order_status_changed",
                "aggregate_type": "order",
                "aggregate_id": str(order_id),
                "payload": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": None,
                    "status": "waiting_for_courier",
                },
                "metadata": {
                    "order_id": str(order_id),
                    "user_id": str(user_id),
                    "courier_user_id": None,
                    "status": "waiting_for_courier",
                },
            }
        )
    )

    with SessionLocal() as verify_db:
        tracked_order = verify_db.get(TrackedOrder, order_id)
        assert tracked_order is not None
        assert tracked_order.user_id == user_id
        assert tracked_order.courier_user_id is None


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
        raise RuntimeError("broken tracking event")

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
