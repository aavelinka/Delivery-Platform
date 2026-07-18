import asyncio
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Courier, CourierAssignment, OutboxEvent
from app.db.session import SessionLocal
from app.domain.enums import CourierAvailability
from app.kafka.consumer import OrderEventsConsumer
from app.schemas.couriers import CourierAvailabilityUpdate, CourierCreate
from app.services.courier_service import CourierService


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
