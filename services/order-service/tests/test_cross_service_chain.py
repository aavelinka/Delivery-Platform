from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Order, OutboxEvent
from app.domain.enums import OrderStatus
from app.kafka.consumer import CourierEventsConsumer

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON = sys.executable
TEST_SECRET = "test-secret"

SERVICE_SETTINGS = {
    "courier-service": {
        "database_env_var": "COURIER_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5433/couriers_test",
        "psycopg_dsn": "postgresql://postgres:postgres@localhost:5433/couriers_test",
        "extra_env": {
            "COURIER_KAFKA_ENABLED": "false",
            "COURIER_JWT_SECRET_KEY": TEST_SECRET,
            "COURIER_CORS_ORIGINS": '["*"]',
        },
    },
    "tracking-service": {
        "database_env_var": "TRACKING_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5437/tracking_test",
        "psycopg_dsn": "postgresql://postgres:postgres@localhost:5437/tracking_test",
        "extra_env": {
            "TRACKING_KAFKA_ENABLED": "false",
            "TRACKING_JWT_SECRET_KEY": TEST_SECRET,
            "TRACKING_CORS_ORIGINS": '["*"]',
        },
    },
    "notification-service": {
        "database_env_var": "NOTIFICATION_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5434/notifications_test",
        "psycopg_dsn": "postgresql://postgres:postgres@localhost:5434/notifications_test",
        "extra_env": {
            "NOTIFICATION_KAFKA_ENABLED": "false",
            "NOTIFICATION_JWT_SECRET_KEY": TEST_SECRET,
            "NOTIFICATION_CORS_ORIGINS": '["*"]',
        },
    },
}

BOOTSTRAP_SCRIPT = """
import json
import os
import sys
from pathlib import Path

repo_root = Path.cwd().parents[1]
shared_lib_root = repo_root / "libs" / "platform-common"
for path in (repo_root, shared_lib_root):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from test_support.postgres import configure_postgres_test_environment

configure_postgres_test_environment(
    database_env_var=os.environ["TEST_DATABASE_ENV_VAR"],
    default_database_url=os.environ["TEST_DATABASE_URL"],
    extra_env=json.loads(os.environ["TEST_EXTRA_ENV_JSON"]),
)
"""


def _service_env(service_name: str) -> dict[str, str]:
    config = SERVICE_SETTINGS[service_name]
    env = os.environ.copy()
    env["TEST_DATABASE_ENV_VAR"] = config["database_env_var"]
    env["TEST_DATABASE_URL"] = config["database_url"]
    env["TEST_EXTRA_ENV_JSON"] = json.dumps(config["extra_env"])
    return env


def _run_service_script(service_name: str, body: str, *, stdin: str = "") -> str:
    script = textwrap.dedent(BOOTSTRAP_SCRIPT + "\n" + body)
    result = subprocess.run(
        [PYTHON, "-c", script],
        cwd=REPO_ROOT / "services" / service_name,
        env=_service_env(service_name),
        input=stdin,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _reset_service_database(service_name: str) -> None:
    _run_service_script(
        service_name,
        """
from test_support.postgres import reset_database
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import engine

reset_database(engine, Base.metadata)
""",
    )


def _create_online_courier() -> dict[str, str]:
    output = _run_service_script(
        "courier-service",
        """
from app.db.session import SessionLocal
from app.domain.enums import CourierAvailability
from app.schemas.couriers import CourierAvailabilityUpdate, CourierCreate
from app.services.courier_service import CourierService
import json
import uuid

with SessionLocal() as db:
    service = CourierService(db)
    courier = service.create_courier(
        CourierCreate(
            user_id=uuid.uuid4(),
            full_name="Alex Smith",
            phone="+375291112233",
            vehicle_type="bike",
            city="Minsk",
        )
    )
    courier = service.change_availability(
        courier.id,
        CourierAvailabilityUpdate(availability=CourierAvailability.ONLINE),
    )
    print(
        json.dumps(
            {
                "courier_id": str(courier.id),
                "courier_user_id": str(courier.user_id),
            }
        )
    )
""",
    )
    return json.loads(output)


def _run_external_consumer(
    service_name: str,
    *,
    consumer_class: str,
    method_name: str,
    event: dict[str, object],
) -> None:
    _run_service_script(
        service_name,
        f"""
from app.core.config import get_settings
from app.kafka.consumer import {consumer_class}
import asyncio
import json
import sys

event = json.loads(sys.stdin.read())
consumer = {consumer_class}(get_settings())
asyncio.run(consumer.{method_name}(event))
""",
        stdin=json.dumps(event),
    )


def _run_external_service_action(service_name: str, body: str, *, stdin: str = "") -> str:
    return _run_service_script(service_name, body, stdin=stdin)


def _fetch_external_one(
    service_name: str,
    query: str,
    params: tuple[object, ...] = (),
) -> dict[str, object] | None:
    with psycopg.connect(
        SERVICE_SETTINGS[service_name]["psycopg_dsn"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()


def _fetch_external_all(
    service_name: str,
    query: str,
    params: tuple[object, ...] = (),
) -> list[dict[str, object]]:
    with psycopg.connect(
        SERVICE_SETTINGS[service_name]["psycopg_dsn"],
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


def _latest_courier_outbox_event(order_id: str, event_type: str) -> dict[str, object]:
    event_row = _fetch_external_one(
        "courier-service",
        """
        SELECT payload
        FROM outbox_events
        WHERE payload->>'event_type' = %s
          AND payload->'metadata'->>'order_id' = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (event_type, order_id),
    )
    assert event_row is not None
    return event_row["payload"]


def _update_courier_assignment_status(assignment_id: str, status: str) -> None:
    _run_external_service_action(
        "courier-service",
        """
from app.db.session import SessionLocal
from app.schemas.couriers import AssignmentStatusUpdate
from app.services.courier_service import CourierService
import json
import sys
import uuid

payload = json.loads(sys.stdin.read())
with SessionLocal() as db:
    CourierService(db).update_assignment_status(
        uuid.UUID(payload["assignment_id"]),
        AssignmentStatusUpdate(status=payload["status"], changed_by="courier"),
    )
""",
        stdin=json.dumps(
            {
                "assignment_id": assignment_id,
                "status": status,
            }
        ),
    )


def test_cross_service_event_chain(client, db_session, auth_headers):
    for service_name in ("courier-service", "tracking-service", "notification-service"):
        _reset_service_database(service_name)

    courier = _create_online_courier()
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=auth_headers(user_id, "customer"),
    )
    assert create_response.status_code == 201

    order_id = create_response.json()["id"]
    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert len(order_outbox_events) == 1
    order_created_event = order_outbox_events[0].payload
    assert order_created_event["event_type"] == "order_created"

    _run_external_consumer(
        "courier-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=order_created_event,
    )

    assignment = _fetch_external_one(
        "courier-service",
        """
        SELECT id::text AS id, courier_id::text AS courier_id, order_id::text AS order_id, status
        FROM courier_assignments
        WHERE order_id = %s
        """,
        (order_id,),
    )
    assert assignment is not None
    assert assignment["courier_id"] == courier["courier_id"]
    assert assignment["order_id"] == order_id
    assert assignment["status"] == "assigned"

    courier_assigned_event = _latest_courier_outbox_event(order_id, "courier_assigned")

    order_consumer = CourierEventsConsumer(get_settings())
    asyncio.run(order_consumer._handle_event(courier_assigned_event))

    db_session.expire_all()
    updated_order = db_session.get(Order, uuid.UUID(order_id))
    assert updated_order is not None
    assert updated_order.status == OrderStatus.COURIER_ASSIGNED
    assert str(updated_order.courier_id) == courier["courier_user_id"]

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
    ]
    propagated_order_event = order_outbox_events[-1].payload

    _run_external_consumer(
        "tracking-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=order_created_event,
    )
    _run_external_consumer(
        "tracking-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=propagated_order_event,
    )
    tracked_order = _fetch_external_one(
        "tracking-service",
        """
        SELECT
            order_id::text AS order_id,
            user_id::text AS user_id,
            courier_user_id::text AS courier_user_id
        FROM tracked_orders
        WHERE order_id = %s
        """,
        (order_id,),
    )
    assert tracked_order is not None
    assert tracked_order["order_id"] == order_id
    assert tracked_order["user_id"] == user_id
    assert tracked_order["courier_user_id"] == courier["courier_user_id"]

    _update_courier_assignment_status(assignment["id"], "accepted")
    assignment_started_event = _latest_courier_outbox_event(order_id, "assignment_status_changed")
    assert assignment_started_event["metadata"]["status"] == "accepted"

    asyncio.run(order_consumer._handle_event(assignment_started_event))

    db_session.expire_all()
    in_delivery_order = db_session.get(Order, uuid.UUID(order_id))
    assert in_delivery_order is not None
    assert in_delivery_order.status == OrderStatus.IN_DELIVERY

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
        "delivery_started",
    ]
    delivery_started_event = order_outbox_events[-1].payload

    _update_courier_assignment_status(assignment["id"], "picked_up")
    assignment_picked_up_event = _latest_courier_outbox_event(order_id, "assignment_status_changed")
    assert assignment_picked_up_event["metadata"]["status"] == "picked_up"

    asyncio.run(order_consumer._handle_event(assignment_picked_up_event))

    db_session.expire_all()
    picked_up_order = db_session.get(Order, uuid.UUID(order_id))
    assert picked_up_order is not None
    assert picked_up_order.status == OrderStatus.IN_DELIVERY

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
        "delivery_started",
    ]

    _update_courier_assignment_status(assignment["id"], "delivered")
    assignment_completed_event = _latest_courier_outbox_event(order_id, "assignment_status_changed")
    assert assignment_completed_event["metadata"]["status"] == "delivered"

    asyncio.run(order_consumer._handle_event(assignment_completed_event))

    db_session.expire_all()
    delivered_order = db_session.get(Order, uuid.UUID(order_id))
    assert delivered_order is not None
    assert delivered_order.status == OrderStatus.DELIVERED
    assert str(delivered_order.courier_id) == courier["courier_user_id"]

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
        "delivery_started",
        "delivery_completed",
    ]
    delivery_completed_event = order_outbox_events[-1].payload

    delivered_assignment = _fetch_external_one(
        "courier-service",
        """
        SELECT status
        FROM courier_assignments
        WHERE id = %s
        """,
        (assignment["id"],),
    )
    assert delivered_assignment is not None
    assert delivered_assignment["status"] == "delivered"

    delivered_courier = _fetch_external_one(
        "courier-service",
        """
        SELECT availability
        FROM couriers
        WHERE id = %s
        """,
        (courier["courier_id"],),
    )
    assert delivered_courier is not None
    assert delivered_courier["availability"] == "online"

    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=order_created_event,
    )
    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=propagated_order_event,
    )
    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=delivery_started_event,
    )
    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=delivery_completed_event,
    )
    notifications = _fetch_external_all(
        "notification-service",
        """
        SELECT
            user_id::text AS user_id,
            title,
            source_event_type,
            aggregate_id
        FROM notifications
        WHERE aggregate_id = %s
        ORDER BY created_at ASC
        """,
        (order_id,),
    )
    assert len(notifications) == 4
    assert [item["source_event_type"] for item in notifications] == [
        "order_created",
        "courier_assigned",
        "delivery_started",
        "delivery_completed",
    ]
    assert [item["title"] for item in notifications] == [
        "Order created",
        "Courier assigned",
        "Delivery started",
        "Delivery completed",
    ]
    assert {item["user_id"] for item in notifications} == {user_id}


def test_cross_service_assignment_cancelled_resets_state(client, db_session, auth_headers):
    for service_name in ("courier-service", "tracking-service", "notification-service"):
        _reset_service_database(service_name)

    courier = _create_online_courier()
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=auth_headers(user_id, "customer"),
    )
    assert create_response.status_code == 201

    order_id = create_response.json()["id"]
    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert len(order_outbox_events) == 1
    order_created_event = order_outbox_events[0].payload

    _run_external_consumer(
        "courier-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=order_created_event,
    )

    assignment = _fetch_external_one(
        "courier-service",
        """
        SELECT id::text AS id, courier_id::text AS courier_id, order_id::text AS order_id, status
        FROM courier_assignments
        WHERE order_id = %s
        """,
        (order_id,),
    )
    assert assignment is not None
    assert assignment["courier_id"] == courier["courier_id"]
    assert assignment["status"] == "assigned"

    courier_assigned_event = _latest_courier_outbox_event(order_id, "courier_assigned")
    order_consumer = CourierEventsConsumer(get_settings())
    asyncio.run(order_consumer._handle_event(courier_assigned_event))

    db_session.expire_all()
    assigned_order = db_session.get(Order, uuid.UUID(order_id))
    assert assigned_order is not None
    assert assigned_order.status == OrderStatus.COURIER_ASSIGNED
    assert str(assigned_order.courier_id) == courier["courier_user_id"]

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
    ]
    propagated_order_event = order_outbox_events[-1].payload

    _run_external_consumer(
        "tracking-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=order_created_event,
    )
    _run_external_consumer(
        "tracking-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=propagated_order_event,
    )

    _update_courier_assignment_status(assignment["id"], "cancelled")
    assignment_cancelled_event = _latest_courier_outbox_event(order_id, "assignment_status_changed")
    assert assignment_cancelled_event["metadata"]["status"] == "cancelled"

    asyncio.run(order_consumer._handle_event(assignment_cancelled_event))

    db_session.expire_all()
    reset_order = db_session.get(Order, uuid.UUID(order_id))
    assert reset_order is not None
    assert reset_order.status == OrderStatus.WAITING_FOR_COURIER
    assert reset_order.courier_id is None

    order_outbox_events = list(
        db_session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
    )
    assert [event.payload["event_type"] for event in order_outbox_events] == [
        "order_created",
        "courier_assigned",
        "order_status_changed",
    ]
    reset_order_event = order_outbox_events[-1].payload
    assert reset_order_event["metadata"]["status"] == "waiting_for_courier"
    assert reset_order_event["metadata"]["courier_user_id"] is None

    cancelled_assignment = _fetch_external_one(
        "courier-service",
        """
        SELECT status
        FROM courier_assignments
        WHERE id = %s
        """,
        (assignment["id"],),
    )
    assert cancelled_assignment is not None
    assert cancelled_assignment["status"] == "cancelled"

    available_courier = _fetch_external_one(
        "courier-service",
        """
        SELECT availability
        FROM couriers
        WHERE id = %s
        """,
        (courier["courier_id"],),
    )
    assert available_courier is not None
    assert available_courier["availability"] == "online"

    _run_external_consumer(
        "tracking-service",
        consumer_class="OrderEventsConsumer",
        method_name="_handle_event",
        event=reset_order_event,
    )
    tracked_order = _fetch_external_one(
        "tracking-service",
        """
        SELECT
            order_id::text AS order_id,
            user_id::text AS user_id,
            courier_user_id::text AS courier_user_id
        FROM tracked_orders
        WHERE order_id = %s
        """,
        (order_id,),
    )
    assert tracked_order is not None
    assert tracked_order["order_id"] == order_id
    assert tracked_order["user_id"] == user_id
    assert tracked_order["courier_user_id"] is None

    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=order_created_event,
    )
    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=propagated_order_event,
    )
    _run_external_consumer(
        "notification-service",
        consumer_class="NotificationConsumer",
        method_name="_handle_message",
        event=reset_order_event,
    )
    notifications = _fetch_external_all(
        "notification-service",
        """
        SELECT
            user_id::text AS user_id,
            title,
            source_event_type,
            aggregate_id
        FROM notifications
        WHERE aggregate_id = %s
        ORDER BY created_at ASC
        """,
        (order_id,),
    )
    assert len(notifications) == 3
    assert [item["source_event_type"] for item in notifications] == [
        "order_created",
        "courier_assigned",
        "order_status_changed",
    ]
    assert [item["title"] for item in notifications] == [
        "Order created",
        "Courier assigned",
        "Order status changed",
    ]
    assert {item["user_id"] for item in notifications} == {user_id}
