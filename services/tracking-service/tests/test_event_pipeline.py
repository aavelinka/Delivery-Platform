import asyncio
import uuid

from app.core.config import get_settings
from app.db.models import TrackedOrder
from app.db.session import SessionLocal
from app.kafka.consumer import OrderEventsConsumer


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
