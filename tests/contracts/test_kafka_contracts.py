from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
TEST_SECRET = "test-secret"
TEST_GATEWAY_SECRET = "test-gateway-secret"

SERVICE_DATABASES = {
    "order-service": {
        "database_env_var": "ORDER_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5438/orders_test",
        "extra_env": {
            "ORDER_JWT_SECRET_KEY": TEST_SECRET,
            "ORDER_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "ORDER_CORS_ORIGINS": '["*"]',
        },
    },
    "courier-service": {
        "database_env_var": "COURIER_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5433/couriers_test",
        "extra_env": {
            "COURIER_JWT_SECRET_KEY": TEST_SECRET,
            "COURIER_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "COURIER_CORS_ORIGINS": '["*"]',
        },
    },
    "tracking-service": {
        "database_env_var": "TRACKING_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5437/tracking_test",
        "extra_env": {
            "TRACKING_JWT_SECRET_KEY": TEST_SECRET,
            "TRACKING_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "TRACKING_CORS_ORIGINS": '["*"]',
        },
    },
    "notification-service": {
        "database_env_var": "NOTIFICATION_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5434/notifications_test",
        "extra_env": {
            "NOTIFICATION_JWT_SECRET_KEY": TEST_SECRET,
            "NOTIFICATION_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "NOTIFICATION_CORS_ORIGINS": '["*"]',
        },
    },
    "payment-service": {
        "database_env_var": "PAYMENT_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5439/payments_test",
        "extra_env": {
            "PAYMENT_JWT_SECRET_KEY": TEST_SECRET,
            "PAYMENT_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "PAYMENT_CORS_ORIGINS": '["*"]',
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

RESET_DATABASE_SCRIPT = """
from test_support.postgres import reset_database
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine

reset_database(engine, Base.metadata)
"""

BUILD_ORDER_CREATED_EVENT_SCRIPT = """
import json
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.db.session import SessionLocal
from app.schemas.orders import OrderCreate
from app.services.order_service import OrderService

user_id = uuid.uuid4()
with SessionLocal() as db:
    service = OrderService(db)
    order, _event = service.create_order(
        OrderCreate(
            user_id=user_id,
            pickup_address="Warehouse A",
            delivery_address="Main street 12",
            total_price=Decimal("149.90"),
        )
    )
    outbox_events = list(db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all())
    order_created_event = next(
        item.payload
        for item in reversed(outbox_events)
        if item.payload["event_type"] == "order_created"
    )
    print(
        json.dumps(
            {
                "order_id": str(order.id),
                "user_id": str(order.user_id),
                "event": order_created_event,
            }
        )
    )
"""

SEED_ONLINE_COURIER_SCRIPT = """
import json
import uuid

from app.db.session import SessionLocal
from app.domain.enums import CourierAvailability
from app.schemas.couriers import CourierAvailabilityUpdate, CourierCreate
from app.services.courier_service import CourierService

with SessionLocal() as db:
    service = CourierService(db)
    courier = service.create_courier(
        CourierCreate(
            user_id=uuid.uuid4(),
            full_name="Contract Courier",
            phone="+375291234567",
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
"""

APPLY_COURIER_ORDER_EVENT_SCRIPT = """
import asyncio
import json
import sys
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import CourierAssignment, OutboxEvent
from app.db.session import SessionLocal
from app.kafka.consumer import OrderEventsConsumer

event = json.loads(sys.stdin.read())
asyncio.run(OrderEventsConsumer(get_settings())._handle_event(event))
order_id = uuid.UUID(str(event["payload"]["order_id"]))

with SessionLocal() as db:
    assignments = list(
        db.scalars(
            select(CourierAssignment).where(CourierAssignment.order_id == order_id)
        ).all()
    )
    assignment = assignments[0] if assignments else None
    outbox_event_types = [
        item.payload["event_type"]
        for item in db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
        if item.payload.get("metadata", {}).get("order_id") == str(order_id)
    ]
    print(
        json.dumps(
            {
                "assignment_count": len(assignments),
                "courier_id": str(assignment.courier_id) if assignment is not None else None,
                "assignment_status": assignment.status.value if assignment is not None else None,
                "outbox_event_types": outbox_event_types,
            }
        )
    )
"""

APPLY_TRACKING_EVENT_SCRIPT = """
import asyncio
import json
import sys
import uuid

from app.core.config import get_settings
from app.db.models import TrackedOrder
from app.db.session import SessionLocal
from app.kafka.consumer import OrderEventsConsumer

event = json.loads(sys.stdin.read())
asyncio.run(OrderEventsConsumer(get_settings())._handle_event(event))
order_id = uuid.UUID(str(event["aggregate_id"]))

with SessionLocal() as db:
    tracked_order = db.get(TrackedOrder, order_id)
    print(
        json.dumps(
            {
                "tracked_order_id": (
                    str(tracked_order.order_id) if tracked_order is not None else None
                ),
                "user_id": str(tracked_order.user_id) if tracked_order is not None else None,
                "courier_user_id": (
                    str(tracked_order.courier_user_id)
                    if tracked_order is not None and tracked_order.courier_user_id is not None
                    else None
                ),
            }
        )
    )
"""

APPLY_NOTIFICATION_EVENT_SCRIPT = """
import asyncio
import json
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Notification
from app.db.session import SessionLocal
from app.kafka.consumer import NotificationConsumer

event = json.loads(sys.stdin.read())
asyncio.run(NotificationConsumer(get_settings())._handle_message(event))

with SessionLocal() as db:
    notifications = list(
        db.scalars(
            select(Notification)
            .where(Notification.source_event_id == str(event["event_id"]))
            .order_by(Notification.created_at.asc())
        ).all()
    )
    notification = notifications[0] if notifications else None
    print(
        json.dumps(
            {
                "count": len(notifications),
                "user_id": str(notification.user_id) if notification is not None else None,
                "title": notification.title if notification is not None else None,
                "message": notification.message if notification is not None else None,
                "source_event_type": (
                    notification.source_event_type if notification is not None else None
                ),
            }
        )
    )
"""

BUILD_COURIER_ASSIGNMENT_EVENTS_SCRIPT = """
import json
import os
import uuid

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.db.session import SessionLocal
from app.domain.enums import AssignmentStatus, CourierAvailability
from app.schemas.couriers import (
    AssignmentCreate,
    AssignmentStatusUpdate,
    CourierAvailabilityUpdate,
    CourierCreate,
)
from app.services.courier_service import CourierService

order_id = uuid.UUID(os.environ["CONTRACT_ORDER_ID"])

with SessionLocal() as db:
    service = CourierService(db)
    courier = service.create_courier(
        CourierCreate(
            user_id=uuid.uuid4(),
            full_name="Contract Courier",
            phone="+375291234567",
            vehicle_type="bike",
            city="Minsk",
        )
    )
    courier = service.change_availability(
        courier.id,
        CourierAvailabilityUpdate(availability=CourierAvailability.ONLINE),
    )
    assignment = service.assign_courier(
        AssignmentCreate(
            courier_id=courier.id,
            order_id=order_id,
        )
    )
    service.update_assignment_status(
        assignment.id,
        AssignmentStatusUpdate(status=AssignmentStatus.ACCEPTED),
    )

    outbox_events = [
        item.payload
        for item in db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
        if item.payload.get("metadata", {}).get("order_id") == str(order_id)
    ]
    courier_assigned_event = next(
        item for item in outbox_events if item["event_type"] == "courier_assigned"
    )
    accepted_event = next(
        item
        for item in outbox_events
        if item["event_type"] == "assignment_status_changed"
        and item["payload"]["status"] == "accepted"
    )
    print(
        json.dumps(
            {
                "courier_user_id": str(courier.user_id),
                "courier_assigned_event": courier_assigned_event,
                "accepted_event": accepted_event,
            }
        )
    )
"""

APPLY_ORDER_COURIER_EVENT_SCRIPT = """
import asyncio
import json
import sys
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Order, OutboxEvent
from app.db.session import SessionLocal
from app.kafka.consumer import CourierEventsConsumer

event = json.loads(sys.stdin.read())
asyncio.run(CourierEventsConsumer(get_settings())._handle_event(event))
order_id = uuid.UUID(str(event["payload"]["order_id"]))

with SessionLocal() as db:
    order = db.get(Order, order_id)
    outbox_event_types = [
        item.payload["event_type"]
        for item in db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all()
        if item.payload.get("metadata", {}).get("order_id") == str(order_id)
    ]
    print(
        json.dumps(
            {
                "order_id": str(order.id) if order is not None else None,
                "courier_user_id": (
                    str(order.courier_id) if order is not None and order.courier_id is not None else None
                ),
                "status": order.status.value if order is not None else None,
                "outbox_event_types": outbox_event_types,
            }
        )
    )
"""

BUILD_PAYMENT_EVENT_SCRIPT = """
import json
import os
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.db.session import SessionLocal
from app.schemas.payments import PaymentConfirm, PaymentCreate, PaymentFail, PaymentRefund
from app.services.payment_service import PaymentService

event_type = os.environ["CONTRACT_PAYMENT_EVENT_TYPE"]
user_id = uuid.uuid4()
order_id = uuid.uuid4()

with SessionLocal() as db:
    service = PaymentService(db)
    payment, _event = service.create_payment(
        PaymentCreate(
            user_id=user_id,
            order_id=order_id,
            amount=Decimal("149.90"),
            currency="USD",
            payment_method="card",
            description="Contract payment",
        )
    )
    if event_type == "payment_confirmed":
        service.confirm_payment(
            payment.id,
            PaymentConfirm(provider_reference="psp-contract-1", changed_by="contracts"),
        )
    elif event_type == "payment_failed":
        service.fail_payment(
            payment.id,
            PaymentFail(reason="Acquirer timeout", changed_by="contracts"),
        )
    elif event_type == "payment_refunded":
        service.confirm_payment(
            payment.id,
            PaymentConfirm(provider_reference="psp-contract-1", changed_by="contracts"),
        )
        service.refund_payment(
            payment.id,
            PaymentRefund(reason="Customer request", changed_by="contracts"),
        )

    outbox_events = list(db.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at.asc())).all())
    matching_event = next(
        item.payload for item in reversed(outbox_events) if item.payload["event_type"] == event_type
    )
    print(
        json.dumps(
            {
                "payment_id": str(payment.id),
                "user_id": str(user_id),
                "order_id": str(order_id),
                "event": matching_event,
            }
        )
    )
"""


def _service_env(service_name: str, *, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    config = SERVICE_DATABASES[service_name]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["TEST_DATABASE_ENV_VAR"] = config["database_env_var"]
    env["TEST_DATABASE_URL"] = config["database_url"]
    env["TEST_EXTRA_ENV_JSON"] = json.dumps(config["extra_env"])

    pythonpath_entries = [
        str(REPO_ROOT),
        str(REPO_ROOT / "libs" / "platform-common"),
    ]
    if existing_pythonpath := env.get("PYTHONPATH"):
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    if extra_env is not None:
        env.update(extra_env)
    return env


def _run_service_python(
    service_name: str,
    body: str,
    *,
    stdin_text: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> str:
    script = textwrap.dedent(BOOTSTRAP_SCRIPT + "\n" + body)
    try:
        result = subprocess.run(
            [PYTHON, "-c", script],
            cwd=REPO_ROOT / "services" / service_name,
            env=_service_env(service_name, extra_env=extra_env),
            input=stdin_text,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"{service_name} subprocess failed\nstdout:\n{exc.stdout}\nstderr:\n{exc.stderr}"
        ) from exc
    return result.stdout.strip()


def _run_service_json(
    service_name: str,
    body: str,
    *,
    stdin_payload: dict[str, object] | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, object]:
    stdout = _run_service_python(
        service_name,
        body,
        stdin_text=json.dumps(stdin_payload) if stdin_payload is not None else None,
        extra_env=extra_env,
    )
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"{service_name} subprocess produced no JSON output")
    return json.loads(lines[-1])


def _reset_service_databases(*service_names: str) -> None:
    for service_name in service_names:
        _run_service_python(service_name, RESET_DATABASE_SCRIPT)


def test_order_created_event_contract_with_courier_consumer() -> None:
    _reset_service_databases("order-service", "courier-service")

    order_event = _run_service_json("order-service", BUILD_ORDER_CREATED_EVENT_SCRIPT)
    seeded_courier = _run_service_json("courier-service", SEED_ONLINE_COURIER_SCRIPT)
    courier_result = _run_service_json(
        "courier-service",
        APPLY_COURIER_ORDER_EVENT_SCRIPT,
        stdin_payload=order_event["event"],
    )

    assert courier_result["assignment_count"] == 1
    assert courier_result["courier_id"] == seeded_courier["courier_id"]
    assert courier_result["assignment_status"] == "assigned"
    assert courier_result["outbox_event_types"] == ["courier_assigned"]


def test_order_created_event_contract_with_tracking_and_notification_consumers() -> None:
    _reset_service_databases("order-service", "tracking-service", "notification-service")

    order_event = _run_service_json("order-service", BUILD_ORDER_CREATED_EVENT_SCRIPT)

    tracking_result = _run_service_json(
        "tracking-service",
        APPLY_TRACKING_EVENT_SCRIPT,
        stdin_payload=order_event["event"],
    )
    notification_result = _run_service_json(
        "notification-service",
        APPLY_NOTIFICATION_EVENT_SCRIPT,
        stdin_payload=order_event["event"],
    )

    assert tracking_result["tracked_order_id"] == order_event["order_id"]
    assert tracking_result["user_id"] == order_event["user_id"]
    assert tracking_result["courier_user_id"] is None

    assert notification_result["count"] == 1
    assert notification_result["user_id"] == order_event["user_id"]
    assert notification_result["title"] == "Order created"
    assert notification_result["source_event_type"] == "order_created"


def test_courier_assignment_event_contract_with_order_and_notification_consumers() -> None:
    _reset_service_databases("order-service", "courier-service", "notification-service")

    order_event = _run_service_json("order-service", BUILD_ORDER_CREATED_EVENT_SCRIPT)
    courier_events = _run_service_json(
        "courier-service",
        BUILD_COURIER_ASSIGNMENT_EVENTS_SCRIPT,
        extra_env={"CONTRACT_ORDER_ID": str(order_event["order_id"])},
    )

    order_assigned_result = _run_service_json(
        "order-service",
        APPLY_ORDER_COURIER_EVENT_SCRIPT,
        stdin_payload=courier_events["courier_assigned_event"],
    )
    order_in_delivery_result = _run_service_json(
        "order-service",
        APPLY_ORDER_COURIER_EVENT_SCRIPT,
        stdin_payload=courier_events["accepted_event"],
    )
    notification_assigned_result = _run_service_json(
        "notification-service",
        APPLY_NOTIFICATION_EVENT_SCRIPT,
        stdin_payload=courier_events["courier_assigned_event"],
    )
    notification_status_result = _run_service_json(
        "notification-service",
        APPLY_NOTIFICATION_EVENT_SCRIPT,
        stdin_payload=courier_events["accepted_event"],
    )

    assert order_assigned_result["status"] == "courier_assigned"
    assert order_assigned_result["courier_user_id"] == courier_events["courier_user_id"]
    assert "courier_assigned" in order_assigned_result["outbox_event_types"]

    assert order_in_delivery_result["status"] == "in_delivery"
    assert order_in_delivery_result["courier_user_id"] == courier_events["courier_user_id"]
    assert "delivery_started" in order_in_delivery_result["outbox_event_types"]

    assert notification_assigned_result["count"] == 1
    assert notification_assigned_result["user_id"] == courier_events["courier_user_id"]
    assert notification_assigned_result["title"] == "Courier assigned"

    assert notification_status_result["count"] == 1
    assert notification_status_result["user_id"] == courier_events["courier_user_id"]
    assert notification_status_result["title"] == "Assignment status changed"


@pytest.mark.parametrize(
    ("event_type", "expected_title", "expected_fragment"),
    [
        ("payment_created", "Payment created", "149.90 USD"),
        ("payment_confirmed", "Payment confirmed", "149.90 USD"),
        ("payment_failed", "Payment failed", "Acquirer timeout"),
        ("payment_refunded", "Payment refunded", "Customer request"),
    ],
)
def test_payment_event_contract_with_notification_consumer(
    event_type: str,
    expected_title: str,
    expected_fragment: str,
) -> None:
    _reset_service_databases("payment-service", "notification-service")

    payment_event = _run_service_json(
        "payment-service",
        BUILD_PAYMENT_EVENT_SCRIPT,
        extra_env={"CONTRACT_PAYMENT_EVENT_TYPE": event_type},
    )
    notification_result = _run_service_json(
        "notification-service",
        APPLY_NOTIFICATION_EVENT_SCRIPT,
        stdin_payload=payment_event["event"],
    )

    assert notification_result["count"] == 1
    assert notification_result["user_id"] == payment_event["user_id"]
    assert notification_result["title"] == expected_title
    assert notification_result["source_event_type"] == event_type
    assert expected_fragment in str(notification_result["message"])
