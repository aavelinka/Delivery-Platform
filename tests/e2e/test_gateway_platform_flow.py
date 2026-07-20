from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
TEST_SECRET = "test-secret"
TEST_GATEWAY_SECRET = "test-gateway-secret"
BOOTSTRAP_ADMIN_EMAIL = "admin@example.com"
BOOTSTRAP_ADMIN_PASSWORD = "super-secure-password"

SERVICE_DATABASES = {
    "auth-service": {
        "database_env_var": "AUTH_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5435/auth_test",
        "extra_env": {
            "AUTH_SECRET_KEY": TEST_SECRET,
            "AUTH_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "AUTH_CORS_ORIGINS": '["*"]',
            "AUTH_BOOTSTRAP_ADMIN_EMAIL": BOOTSTRAP_ADMIN_EMAIL,
            "AUTH_BOOTSTRAP_ADMIN_PASSWORD": BOOTSTRAP_ADMIN_PASSWORD,
            "AUTH_BOOTSTRAP_ADMIN_FULL_NAME": "Platform Administrator",
        },
    },
    "user-service": {
        "database_env_var": "USER_DATABASE_URL",
        "database_url": "postgresql+psycopg://postgres:postgres@localhost:5436/users_test",
        "extra_env": {
            "USER_JWT_SECRET_KEY": TEST_SECRET,
            "USER_GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
            "USER_CORS_ORIGINS": '["*"]',
        },
    },
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


@dataclass
class RunningService:
    name: str
    port: int
    process: subprocess.Popen[str]
    log_path: Path
    log_handle: object


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _run_service_script(service_name: str, body: str) -> None:
    config = SERVICE_DATABASES[service_name]
    env = os.environ.copy()
    env["TEST_DATABASE_ENV_VAR"] = config["database_env_var"]
    env["TEST_DATABASE_URL"] = config["database_url"]
    env["TEST_EXTRA_ENV_JSON"] = json.dumps(config["extra_env"])
    script = textwrap.dedent(BOOTSTRAP_SCRIPT + "\n" + body)
    subprocess.run(
        [PYTHON, "-c", script],
        cwd=REPO_ROOT / "services" / service_name,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


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


def _service_env(
    service_name: str,
    *,
    port: int,
    ports: dict[str, int],
    topic_suffix: str,
) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["JWT_SECRET_KEY"] = TEST_SECRET
    env["GATEWAY_INTERNAL_SECRET"] = TEST_GATEWAY_SECRET
    pythonpath_entries = [
        str(REPO_ROOT),
        str(REPO_ROOT / "libs" / "platform-common"),
    ]
    if existing_pythonpath := env.get("PYTHONPATH"):
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    if service_name == "api-gateway":
        env.update(
            {
                "GATEWAY_SERVICE_NAME": "api-gateway",
                "GATEWAY_ENVIRONMENT": "test",
                "GATEWAY_JWT_SECRET_KEY": TEST_SECRET,
                "GATEWAY_INTERNAL_SECRET": TEST_GATEWAY_SECRET,
                "GATEWAY_AUTH_SERVICE_URL": f"http://127.0.0.1:{ports['auth-service']}",
                "GATEWAY_USER_SERVICE_URL": f"http://127.0.0.1:{ports['user-service']}",
                "GATEWAY_ORDER_SERVICE_URL": f"http://127.0.0.1:{ports['order-service']}",
                "GATEWAY_COURIER_SERVICE_URL": f"http://127.0.0.1:{ports['courier-service']}",
                "GATEWAY_TRACKING_SERVICE_URL": f"http://127.0.0.1:{ports['tracking-service']}",
                "GATEWAY_NOTIFICATION_SERVICE_URL": (
                    f"http://127.0.0.1:{ports['notification-service']}"
                ),
                "GATEWAY_PAYMENT_SERVICE_URL": f"http://127.0.0.1:{ports['payment-service']}",
                "GATEWAY_RATE_LIMIT_REQUESTS": "1000",
                "GATEWAY_REQUEST_TIMEOUT_SECONDS": "5",
                "GATEWAY_RETRY_ATTEMPTS": "2",
                "GATEWAY_RETRY_BACKOFF_SECONDS": "0.1",
            }
        )
        return env

    config = SERVICE_DATABASES[service_name]
    env[config["database_env_var"]] = config["database_url"]
    env.update(config["extra_env"])

    kafka_orders_topic = f"orders.e2e.{topic_suffix}"
    kafka_couriers_topic = f"couriers.e2e.{topic_suffix}"
    kafka_payments_topic = f"payments.e2e.{topic_suffix}"

    if service_name == "auth-service":
        return env

    if service_name == "user-service":
        return env

    if service_name == "order-service":
        env.update(
            {
                "ORDER_KAFKA_ENABLED": "true",
                "ORDER_KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092",
                "ORDER_KAFKA_CLIENT_ID": f"order-service-e2e-{topic_suffix}",
                "ORDER_KAFKA_GROUP_ID": f"order-service-e2e-{topic_suffix}",
                "ORDER_KAFKA_ORDERS_TOPIC": kafka_orders_topic,
                "ORDER_KAFKA_COURIERS_TOPIC": kafka_couriers_topic,
            }
        )
        return env

    if service_name == "courier-service":
        env.update(
            {
                "COURIER_KAFKA_ENABLED": "true",
                "COURIER_KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092",
                "COURIER_KAFKA_CLIENT_ID": f"courier-service-e2e-{topic_suffix}",
                "COURIER_KAFKA_GROUP_ID": f"courier-service-e2e-{topic_suffix}",
                "COURIER_KAFKA_ORDERS_TOPIC": kafka_orders_topic,
                "COURIER_KAFKA_COURIERS_TOPIC": kafka_couriers_topic,
            }
        )
        return env

    if service_name == "tracking-service":
        env.update(
            {
                "TRACKING_KAFKA_ENABLED": "true",
                "TRACKING_KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092",
                "TRACKING_KAFKA_CLIENT_ID": f"tracking-service-e2e-{topic_suffix}",
                "TRACKING_KAFKA_GROUP_ID": f"tracking-service-e2e-{topic_suffix}",
                "TRACKING_KAFKA_ORDERS_TOPIC": kafka_orders_topic,
                "TRACKING_KAFKA_TOPIC": f"tracking.e2e.{topic_suffix}",
            }
        )
        return env

    if service_name == "notification-service":
        env.update(
            {
                "NOTIFICATION_KAFKA_ENABLED": "true",
                "NOTIFICATION_KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092",
                "NOTIFICATION_KAFKA_CLIENT_ID": f"notification-service-e2e-{topic_suffix}",
                "NOTIFICATION_KAFKA_GROUP_ID": f"notification-service-e2e-{topic_suffix}",
                "NOTIFICATION_KAFKA_TOPICS": json.dumps(
                    [kafka_orders_topic, kafka_couriers_topic, kafka_payments_topic]
                ),
            }
        )
        return env

    if service_name == "payment-service":
        env.update(
            {
                "PAYMENT_KAFKA_ENABLED": "true",
                "PAYMENT_KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092",
                "PAYMENT_KAFKA_CLIENT_ID": f"payment-service-e2e-{topic_suffix}",
                "PAYMENT_KAFKA_PAYMENTS_TOPIC": kafka_payments_topic,
            }
        )
        return env

    raise ValueError(f"Unknown service {service_name!r}")


def _wait_for_http(
    url: str,
    *,
    timeout: float = 20.0,
) -> None:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=1.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
            except httpx.HTTPError:
                time.sleep(0.5)
                continue
            if response.status_code == 200:
                return
            time.sleep(0.5)
    raise AssertionError(f"Timed out waiting for {url}")


def _service_log_tail(log_path: Path, *, lines: int = 80) -> str:
    if not log_path.exists():
        return ""
    content = log_path.read_text()
    return "\n".join(content.splitlines()[-lines:])


def _start_service(
    service_name: str,
    *,
    port: int,
    ports: dict[str, int],
    topic_suffix: str,
    logs_dir: Path,
) -> RunningService:
    service_dir = REPO_ROOT / "services" / service_name
    log_path = logs_dir / f"{service_name}.log"
    env = _service_env(
        service_name,
        port=port,
        ports=ports,
        topic_suffix=topic_suffix,
    )

    for attempt in range(1, 6):
        log_handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [
                PYTHON,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=service_dir,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                _wait_for_http(f"http://127.0.0.1:{port}/health", timeout=1.0)
            except AssertionError:
                time.sleep(0.5)
                continue
            return RunningService(
                name=service_name,
                port=port,
                process=process,
                log_path=log_path,
                log_handle=log_handle,
            )

        if process.poll() is None:
            process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

        log_handle.close()
        if attempt < 5:
            time.sleep(2)
            continue
        raise AssertionError(
            f"Service {service_name} failed to start.\n{_service_log_tail(log_path)}"
        )

    raise AssertionError(f"Service {service_name} failed to become healthy")


def _stop_service(service: RunningService) -> None:
    if service.process.poll() is None:
        service.process.terminate()
        try:
            service.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            service.process.kill()
            service.process.wait(timeout=10)
    service.log_handle.close()


def _authorized_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wait_until(description: str, func, *, timeout: float = 60.0, interval: float = 1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = func()
        if result is not None:
            return result
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for {description}")


@contextlib.contextmanager
def _running_platform_client():
    for service_name in SERVICE_DATABASES:
        _reset_service_database(service_name)

    topic_suffix = uuid.uuid4().hex[:8]
    ports = {
        "auth-service": _free_port(),
        "user-service": _free_port(),
        "order-service": _free_port(),
        "courier-service": _free_port(),
        "tracking-service": _free_port(),
        "notification-service": _free_port(),
        "payment-service": _free_port(),
        "api-gateway": _free_port(),
    }

    with tempfile.TemporaryDirectory(prefix="gateway-e2e-logs-") as logs_dir_raw:
        logs_dir = Path(logs_dir_raw)
        running_services: list[RunningService] = []
        try:
            for service_name in (
                "auth-service",
                "user-service",
                "order-service",
                "courier-service",
                "tracking-service",
                "notification-service",
                "payment-service",
                "api-gateway",
            ):
                running_services.append(
                    _start_service(
                        service_name,
                        port=ports[service_name],
                        ports=ports,
                        topic_suffix=topic_suffix,
                        logs_dir=logs_dir,
                    )
                )

            gateway_url = f"http://127.0.0.1:{ports['api-gateway']}"
            with httpx.Client(base_url=gateway_url, timeout=10.0, trust_env=False) as client:
                yield client
        finally:
            failure_logs: list[str] = []
            for service in reversed(running_services):
                if service.process.poll() not in {None, 0}:
                    failure_logs.append(
                        f"== {service.name} ==\n{_service_log_tail(service.log_path)}"
                    )
                _stop_service(service)
            if failure_logs:
                raise AssertionError("\n\n".join(failure_logs))


def _bootstrap_customer_and_online_courier(client: httpx.Client) -> dict[str, object]:
    admin_login = client.post(
        "/auth/login",
        json={
            "email": BOOTSTRAP_ADMIN_EMAIL,
            "password": BOOTSTRAP_ADMIN_PASSWORD,
        },
    )
    assert admin_login.status_code == 200
    admin_headers = _authorized_headers(admin_login.json()["access_token"])

    courier_register = client.post(
        "/auth/register",
        json={
            "email": "courier@example.com",
            "password": "strong-password",
            "full_name": "Courier Rider",
        },
    )
    assert courier_register.status_code == 201
    courier_user = courier_register.json()["user"]

    customer_register = client.post(
        "/auth/register",
        json={
            "email": "customer@example.com",
            "password": "strong-password",
            "full_name": "Customer One",
        },
    )
    assert customer_register.status_code == 201
    customer_payload = customer_register.json()
    customer_user = customer_payload["user"]

    promote_courier = client.patch(
        f"/auth/users/{courier_user['id']}/role",
        json={"role": "courier"},
        headers=admin_headers,
    )
    assert promote_courier.status_code == 200
    assert promote_courier.json()["role"] == "courier"

    courier_login = client.post(
        "/auth/login",
        json={
            "email": "courier@example.com",
            "password": "strong-password",
        },
    )
    assert courier_login.status_code == 200
    courier_headers = _authorized_headers(courier_login.json()["access_token"])
    customer_headers = _authorized_headers(customer_payload["access_token"])

    create_courier = client.post(
        "/couriers",
        json={
            "user_id": courier_user["id"],
            "full_name": "Courier Rider",
            "phone": "+375291234567",
            "vehicle_type": "bike",
            "city": "Minsk",
        },
        headers=courier_headers,
    )
    assert create_courier.status_code == 201
    courier = create_courier.json()

    set_online = client.patch(
        f"/couriers/{courier['id']}/availability",
        json={"availability": "online"},
        headers=courier_headers,
    )
    assert set_online.status_code == 200
    assert set_online.json()["availability"] == "online"

    return {
        "admin_headers": admin_headers,
        "courier": courier,
        "courier_headers": courier_headers,
        "courier_user": courier_user,
        "customer_headers": customer_headers,
        "customer_user": customer_user,
    }


def test_gateway_platform_flow_end_to_end():
    with _running_platform_client() as client:
        platform = _bootstrap_customer_and_online_courier(client)
        courier = platform["courier"]
        admin_headers = platform["admin_headers"]
        courier_headers = platform["courier_headers"]
        courier_user = platform["courier_user"]
        customer_headers = platform["customer_headers"]
        customer_user = platform["customer_user"]

        update_profile = client.patch(
            f"/users/{customer_user['id']}",
            json={
                "full_name": "Customer Updated",
                "phone": "+375291112233",
                "email": "customer.profile@example.com",
            },
            headers=customer_headers,
        )
        assert update_profile.status_code == 200
        assert update_profile.json()["full_name"] == "Customer Updated"

        create_address = client.post(
            f"/users/{customer_user['id']}/addresses",
            json={
                "label": "Home",
                "city": "Minsk",
                "street": "Main street",
                "building": "12A",
                "apartment": "34",
                "comment": "Ring the bell",
                "is_default": True,
            },
            headers=customer_headers,
        )
        assert create_address.status_code == 201
        assert create_address.json()["city"] == "Minsk"

        available_couriers = client.get(
            "/couriers/available",
            headers=customer_headers,
        )
        assert available_couriers.status_code == 200
        assert available_couriers.json()["total"] == 1

        create_order = client.post(
            "/orders",
            json={
                "user_id": customer_user["id"],
                "pickup_address": "Warehouse A",
                "delivery_address": "Main street 12",
                "total_price": "149.90",
            },
            headers=customer_headers,
        )
        assert create_order.status_code == 201
        order = create_order.json()
        order_id = order["id"]

        create_payment = client.post(
            "/payments",
            json={
                "user_id": customer_user["id"],
                "order_id": order_id,
                "amount": "149.90",
                "currency": "USD",
                "payment_method": "card",
                "description": "Gateway e2e order payment",
            },
            headers=customer_headers,
        )
        assert create_payment.status_code == 201
        payment = create_payment.json()
        payment_id = payment["id"]
        assert payment["status"] == "pending"

        get_payment = client.get(
            f"/payments/{payment_id}",
            headers=customer_headers,
        )
        assert get_payment.status_code == 200
        assert get_payment.json()["order_id"] == order_id

        customer_payments = client.get("/payments", headers=customer_headers)
        assert customer_payments.status_code == 200
        assert customer_payments.json()["total"] == 1
        assert customer_payments.json()["items"][0]["id"] == payment_id

        confirm_payment = client.post(
            f"/payments/{payment_id}/confirm",
            json={"provider_reference": "psp-e2e-1", "changed_by": "admin"},
            headers=admin_headers,
        )
        assert confirm_payment.status_code == 200
        assert confirm_payment.json()["status"] == "confirmed"
        assert confirm_payment.json()["provider_reference"] == "psp-e2e-1"

        assigned_order = _wait_until(
            "order assignment",
            lambda: _poll_order_assigned(
                client,
                order_id=order_id,
                courier_user_id=courier_user["id"],
                headers=customer_headers,
            ),
            timeout=90.0,
        )
        assert assigned_order["status"] == "courier_assigned"

        courier_orders = client.get("/orders", headers=courier_headers)
        assert courier_orders.status_code == 200
        assert courier_orders.json()["total"] == 1
        assert courier_orders.json()["items"][0]["id"] == order_id

        assignment = _wait_until(
            "courier assignment record",
            lambda: _poll_assignment(
                client,
                courier_id=courier["id"],
                order_id=order_id,
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert assignment["status"] == "assigned"

        accept_assignment = client.patch(
            f"/couriers/assignments/{assignment['id']}/status",
            json={"status": "accepted"},
            headers=courier_headers,
        )
        assert accept_assignment.status_code == 200
        assert accept_assignment.json()["status"] == "accepted"

        in_delivery_order = _wait_until(
            "order in delivery",
            lambda: _poll_order_status(
                client,
                order_id=order_id,
                expected_status="in_delivery",
                headers=customer_headers,
            ),
            timeout=90.0,
        )
        assert in_delivery_order["courier_user_id"] == courier_user["id"]

        create_location = client.post(
            "/tracking/locations",
            json={
                "courier_user_id": courier_user["id"],
                "order_id": order_id,
                "latitude": 53.9045,
                "longitude": 27.5615,
                "accuracy_meters": 10,
            },
            headers=courier_headers,
        )
        assert create_location.status_code == 201
        assert create_location.json()["order_id"] == order_id

        order_location = _wait_until(
            "tracked order location",
            lambda: _poll_order_location(
                client,
                order_id=order_id,
                headers=customer_headers,
            ),
            timeout=30.0,
        )
        assert order_location["courier_user_id"] == courier_user["id"]
        assert order_location["user_id"] == customer_user["id"]

        order_history = client.get(
            f"/tracking/orders/{order_id}/history",
            headers=customer_headers,
        )
        assert order_history.status_code == 200
        assert len(order_history.json()) >= 1

        pick_up_assignment = client.patch(
            f"/couriers/assignments/{assignment['id']}/status",
            json={"status": "picked_up"},
            headers=courier_headers,
        )
        assert pick_up_assignment.status_code == 200
        assert pick_up_assignment.json()["status"] == "picked_up"

        still_in_delivery_order = _wait_until(
            "order remains in delivery after pickup",
            lambda: _poll_order_status(
                client,
                order_id=order_id,
                expected_status="in_delivery",
                headers=customer_headers,
            ),
            timeout=60.0,
        )
        assert still_in_delivery_order["courier_user_id"] == courier_user["id"]

        deliver_assignment = client.patch(
            f"/couriers/assignments/{assignment['id']}/status",
            json={"status": "delivered"},
            headers=courier_headers,
        )
        assert deliver_assignment.status_code == 200
        assert deliver_assignment.json()["status"] == "delivered"

        delivered_order = _wait_until(
            "order delivery completion",
            lambda: _poll_order_status(
                client,
                order_id=order_id,
                expected_status="delivered",
                headers=customer_headers,
            ),
            timeout=90.0,
        )
        assert delivered_order["courier_user_id"] == courier_user["id"]

        delivered_courier = _wait_until(
            "courier availability reset",
            lambda: _poll_courier_availability(
                client,
                courier_id=courier["id"],
                expected="online",
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert delivered_courier["availability"] == "online"

        customer_notifications = _wait_until(
            "customer notifications",
            lambda: _poll_notifications(
                client,
                user_id=customer_user["id"],
                headers=customer_headers,
                expected_titles={
                    "Order created",
                    "Courier assigned",
                    "Delivery started",
                    "Delivery completed",
                    "Payment created",
                    "Payment confirmed",
                },
            ),
            timeout=90.0,
        )
        titles = {item["title"] for item in customer_notifications["items"]}
        assert {
            "Order created",
            "Courier assigned",
            "Delivery started",
            "Delivery completed",
            "Payment created",
            "Payment confirmed",
        }.issubset(titles)

        first_notification_id = customer_notifications["items"][0]["id"]
        mark_read = client.patch(
            f"/notifications/{first_notification_id}/read",
            headers=customer_headers,
        )
        assert mark_read.status_code == 200
        assert mark_read.json()["status"] == "read"

        unread_notifications = client.get(
            f"/notifications/users/{customer_user['id']}",
            params={"unread_only": "true"},
            headers=customer_headers,
        )
        assert unread_notifications.status_code == 200
        assert unread_notifications.json()["total"] >= 3
        assert all(
            item["id"] != first_notification_id
            for item in unread_notifications.json()["items"]
        )

        order_events = client.get(
            f"/orders/{order_id}/events",
            headers=customer_headers,
        )
        assert order_events.status_code == 200
        event_types = [item["event_type"] for item in order_events.json()]
        assert event_types == [
            "order_created",
            "courier_assigned",
            "delivery_started",
            "delivery_completed",
        ]

        payment_events = client.get(
            f"/payments/{payment_id}/events",
            headers=customer_headers,
        )
        assert payment_events.status_code == 200
        payment_event_types = [item["event_type"] for item in payment_events.json()]
        assert payment_event_types == [
            "payment_created",
            "payment_confirmed",
        ]


def test_gateway_assignment_cancelled_resets_order_to_queue():
    with _running_platform_client() as client:
        platform = _bootstrap_customer_and_online_courier(client)
        courier = platform["courier"]
        courier_headers = platform["courier_headers"]
        courier_user = platform["courier_user"]
        customer_headers = platform["customer_headers"]
        customer_user = platform["customer_user"]

        available_couriers = client.get(
            "/couriers/available",
            headers=customer_headers,
        )
        assert available_couriers.status_code == 200
        assert available_couriers.json()["total"] == 1

        create_order = client.post(
            "/orders",
            json={
                "user_id": customer_user["id"],
                "pickup_address": "Warehouse A",
                "delivery_address": "Main street 12",
                "total_price": "149.90",
            },
            headers=customer_headers,
        )
        assert create_order.status_code == 201
        order_id = create_order.json()["id"]

        assigned_order = _wait_until(
            "order assignment",
            lambda: _poll_order_assigned(
                client,
                order_id=order_id,
                courier_user_id=courier_user["id"],
                headers=customer_headers,
            ),
            timeout=90.0,
        )
        assert assigned_order["status"] == "courier_assigned"

        assignment = _wait_until(
            "courier assignment record",
            lambda: _poll_assignment(
                client,
                courier_id=courier["id"],
                order_id=order_id,
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert assignment["status"] == "assigned"

        cancel_assignment = client.patch(
            f"/couriers/assignments/{assignment['id']}/status",
            json={"status": "cancelled"},
            headers=courier_headers,
        )
        assert cancel_assignment.status_code == 200
        assert cancel_assignment.json()["status"] == "cancelled"

        reset_order = _wait_until(
            "order reset to waiting for courier",
            lambda: _poll_order_status(
                client,
                order_id=order_id,
                expected_status="waiting_for_courier",
                headers=customer_headers,
            ),
            timeout=90.0,
        )
        assert reset_order["courier_user_id"] is None

        cancelled_assignment = _wait_until(
            "cancelled assignment",
            lambda: _poll_assignment_status(
                client,
                courier_id=courier["id"],
                order_id=order_id,
                expected_status="cancelled",
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert cancelled_assignment["status"] == "cancelled"

        reset_courier = _wait_until(
            "courier availability reset after cancellation",
            lambda: _poll_courier_availability(
                client,
                courier_id=courier["id"],
                expected="online",
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert reset_courier["availability"] == "online"

        denied_order_access = _wait_until(
            "courier order access revoked",
            lambda: _poll_response_status(
                client,
                path=f"/orders/{order_id}",
                expected_status_code=403,
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert denied_order_access.status_code == 403

        empty_courier_orders = _wait_until(
            "courier order list cleared",
            lambda: _poll_order_list_total(
                client,
                expected_total=0,
                headers=courier_headers,
            ),
            timeout=60.0,
        )
        assert empty_courier_orders["total"] == 0

        available_again = _wait_until(
            "courier becomes available again",
            lambda: _poll_available_courier(
                client,
                courier_id=courier["id"],
                headers=customer_headers,
            ),
            timeout=60.0,
        )
        assert available_again["total"] == 1
        assert available_again["items"][0]["id"] == courier["id"]

        customer_notifications = _wait_until(
            "customer cancellation notifications",
            lambda: _poll_notifications(
                client,
                user_id=customer_user["id"],
                headers=customer_headers,
                expected_titles={
                    "Order created",
                    "Courier assigned",
                    "Order status changed",
                },
            ),
            timeout=90.0,
        )
        assert customer_notifications["total"] == 3
        customer_titles = {item["title"] for item in customer_notifications["items"]}
        assert customer_titles == {
            "Order created",
            "Courier assigned",
            "Order status changed",
        }

        courier_notifications = _wait_until(
            "courier cancellation notification",
            lambda: _poll_notifications(
                client,
                user_id=courier_user["id"],
                headers=courier_headers,
                expected_titles={"Assignment status changed"},
            ),
            timeout=90.0,
        )
        courier_titles = {item["title"] for item in courier_notifications["items"]}
        assert "Assignment status changed" in courier_titles

        order_events = client.get(
            f"/orders/{order_id}/events",
            headers=customer_headers,
        )
        assert order_events.status_code == 200
        event_types = [item["event_type"] for item in order_events.json()]
        assert event_types == [
            "order_created",
            "courier_assigned",
            "order_status_changed",
        ]


def _poll_order_assigned(
    client: httpx.Client,
    *,
    order_id: str,
    courier_user_id: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get(f"/orders/{order_id}", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    if payload["status"] != "courier_assigned":
        return None
    if payload["courier_user_id"] != courier_user_id:
        return None
    return payload


def _poll_order_status(
    client: httpx.Client,
    *,
    order_id: str,
    expected_status: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get(f"/orders/{order_id}", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    if payload["status"] != expected_status:
        return None
    return payload


def _poll_assignment(
    client: httpx.Client,
    *,
    courier_id: str,
    order_id: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get(f"/couriers/{courier_id}/assignments", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    for item in payload["items"]:
        if item["order_id"] == order_id:
            return item
    return None


def _poll_assignment_status(
    client: httpx.Client,
    *,
    courier_id: str,
    order_id: str,
    expected_status: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    assignment = _poll_assignment(
        client,
        courier_id=courier_id,
        order_id=order_id,
        headers=headers,
    )
    if assignment is None:
        return None
    if assignment["status"] != expected_status:
        return None
    return assignment


def _poll_order_location(
    client: httpx.Client,
    *,
    order_id: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get(f"/tracking/orders/{order_id}", headers=headers)
    if response.status_code != 200:
        return None
    return response.json()


def _poll_courier_availability(
    client: httpx.Client,
    *,
    courier_id: str,
    expected: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get(f"/couriers/{courier_id}", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    if payload["availability"] != expected:
        return None
    return payload


def _poll_order_list_total(
    client: httpx.Client,
    *,
    expected_total: int,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get("/orders", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    if payload["total"] != expected_total:
        return None
    return payload


def _poll_available_courier(
    client: httpx.Client,
    *,
    courier_id: str,
    headers: dict[str, str],
) -> dict[str, object] | None:
    response = client.get("/couriers/available", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    if not any(item["id"] == courier_id for item in payload["items"]):
        return None
    return payload


def _poll_response_status(
    client: httpx.Client,
    *,
    path: str,
    expected_status_code: int,
    headers: dict[str, str],
) -> httpx.Response | None:
    response = client.get(path, headers=headers)
    if response.status_code != expected_status_code:
        return None
    return response


def _poll_notifications(
    client: httpx.Client,
    *,
    user_id: str,
    headers: dict[str, str],
    expected_titles: set[str] | None = None,
) -> dict[str, object] | None:
    response = client.get(f"/notifications/users/{user_id}", headers=headers)
    if response.status_code != 200:
        return None
    payload = response.json()
    titles = {item["title"] for item in payload["items"]}
    if expected_titles is None:
        expected_titles = {
            "Order created",
            "Courier assigned",
            "Delivery started",
            "Delivery completed",
        }
    if not expected_titles.issubset(titles):
        return None
    return payload
