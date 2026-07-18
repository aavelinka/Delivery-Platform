import asyncio
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Notification
from app.db.session import SessionLocal
from app.kafka.consumer import NotificationConsumer


def test_notification_consumer_creates_single_notification_for_replayed_event():
    event_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    consumer = NotificationConsumer(get_settings())
    event = {
        "event_id": str(event_id),
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

    asyncio.run(consumer._handle_message(event))
    asyncio.run(consumer._handle_message(event))

    with SessionLocal() as verify_db:
        notifications = list(
            verify_db.scalars(
                select(Notification).where(Notification.source_event_id == str(event_id))
            ).all()
        )
        assert len(notifications) == 1
        assert notifications[0].user_id == user_id
        assert notifications[0].source_event_type == "order_created"


def test_notification_consumer_creates_notification_from_courier_event():
    event_id = uuid.uuid4()
    courier_user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    consumer = NotificationConsumer(get_settings())
    event = {
        "event_id": str(event_id),
        "event_type": "assignment_status_changed",
        "aggregate_type": "assignment",
        "aggregate_id": str(uuid.uuid4()),
        "payload": {
            "order_id": str(order_id),
        },
        "metadata": {
            "order_id": str(order_id),
            "courier_user_id": str(courier_user_id),
            "status": "accepted",
        },
    }

    asyncio.run(consumer._handle_message(event))

    with SessionLocal() as verify_db:
        notifications = list(
            verify_db.scalars(
                select(Notification).where(Notification.source_event_id == str(event_id))
            ).all()
        )
        assert len(notifications) == 1
        assert notifications[0].user_id == courier_user_id
        assert notifications[0].source_event_type == "assignment_status_changed"
