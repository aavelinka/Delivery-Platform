import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db.models import OutboxEvent


def _payment_payload(user_id: str, order_id: str | None = None) -> dict[str, str]:
    return {
        "user_id": user_id,
        "order_id": order_id or str(uuid.uuid4()),
        "amount": "199.90",
        "currency": "usd",
        "payment_method": "card",
        "description": "Order checkout",
    }


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_create_get_and_list_payment(client, auth_headers):
    user_id = str(uuid.uuid4())
    payload = _payment_payload(user_id)

    create_response = client.post(
        "/payments",
        json=payload,
        headers=auth_headers(user_id, "customer"),
    )
    assert create_response.status_code == 201
    payment = create_response.json()
    assert payment["user_id"] == user_id
    assert payment["status"] == "pending"
    assert payment["currency"] == "USD"

    payment_id = payment["id"]

    get_response = client.get(f"/payments/{payment_id}", headers=auth_headers(user_id, "customer"))
    assert get_response.status_code == 200
    assert get_response.json()["id"] == payment_id

    list_response = client.get("/payments", headers=auth_headers(user_id, "customer"))
    assert list_response.status_code == 200
    data = list_response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == payment_id


def test_create_payment_writes_outbox_event(client, db_session, auth_headers):
    user_id = str(uuid.uuid4())
    response = client.post(
        "/payments",
        json=_payment_payload(user_id),
        headers=auth_headers(user_id, "customer"),
    )

    assert response.status_code == 201
    outbox_event = db_session.scalar(select(OutboxEvent))
    assert outbox_event is not None
    assert outbox_event.status == "pending"
    assert outbox_event.topic == "payments.events"
    assert outbox_event.payload["event_type"] == "payment_created"


def test_confirm_payment(client, auth_headers):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/payments",
        json=_payment_payload(user_id),
        headers=auth_headers(user_id, "customer"),
    )
    payment_id = create_response.json()["id"]

    confirm_response = client.post(
        f"/payments/{payment_id}/confirm",
        json={"provider_reference": "psp-123", "changed_by": "admin"},
        headers=auth_headers(role="admin"),
    )

    assert confirm_response.status_code == 200
    payment = confirm_response.json()
    assert payment["status"] == "confirmed"
    assert payment["provider_reference"] == "psp-123"


def test_fail_payment_and_events(client, auth_headers):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/payments",
        json=_payment_payload(user_id),
        headers=auth_headers(user_id, "customer"),
    )
    payment_id = create_response.json()["id"]

    fail_response = client.post(
        f"/payments/{payment_id}/fail",
        json={"reason": "Acquirer timeout", "changed_by": "admin"},
        headers=auth_headers(role="admin"),
    )
    assert fail_response.status_code == 200
    assert fail_response.json()["status"] == "failed"
    assert fail_response.json()["failure_reason"] == "Acquirer timeout"

    events_response = client.get(
        f"/payments/{payment_id}/events",
        headers=auth_headers(user_id, "customer"),
    )
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "payment_created"
    assert events[1]["event_type"] == "payment_failed"


def test_refund_payment(client, auth_headers):
    user_id = str(uuid.uuid4())
    create_response = client.post(
        "/payments",
        json=_payment_payload(user_id),
        headers=auth_headers(user_id, "customer"),
    )
    payment_id = create_response.json()["id"]

    confirm_response = client.post(
        f"/payments/{payment_id}/confirm",
        json={"provider_reference": "psp-123"},
        headers=auth_headers(role="admin"),
    )
    assert confirm_response.status_code == 200

    refund_response = client.post(
        f"/payments/{payment_id}/refund",
        json={"reason": "Customer cancellation", "changed_by": "admin"},
        headers=auth_headers(role="admin"),
    )
    assert refund_response.status_code == 200
    assert refund_response.json()["status"] == "refunded"


def test_duplicate_active_payment_is_rejected(client, auth_headers):
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    headers = auth_headers(user_id, "customer")
    response = client.post("/payments", json=_payment_payload(user_id, order_id), headers=headers)
    assert response.status_code == 201

    duplicate_response = client.post(
        "/payments",
        json=_payment_payload(user_id, order_id),
        headers=headers,
    )
    assert duplicate_response.status_code == 409


def test_customer_cannot_access_foreign_payment(client, auth_headers):
    owner_user_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())
    create_response = client.post(
        "/payments",
        json=_payment_payload(owner_user_id),
        headers=auth_headers(owner_user_id, "customer"),
    )
    payment_id = create_response.json()["id"]

    response = client.get(
        f"/payments/{payment_id}",
        headers=auth_headers(other_user_id, "customer"),
    )
    assert response.status_code == 403


def test_admin_summary_returns_status_counts_and_amounts(client, auth_headers):
    customer_id = str(uuid.uuid4())
    first_payment = client.post(
        "/payments",
        json=_payment_payload(customer_id, str(uuid.uuid4())),
        headers=auth_headers(customer_id, "customer"),
    )
    second_payment = client.post(
        "/payments",
        json=_payment_payload(customer_id, str(uuid.uuid4())),
        headers=auth_headers(customer_id, "customer"),
    )

    client.post(
        f"/payments/{first_payment.json()['id']}/confirm",
        json={"provider_reference": "psp-1"},
        headers=auth_headers(role="admin"),
    )
    client.post(
        f"/payments/{second_payment.json()['id']}/fail",
        json={"reason": "Insufficient funds"},
        headers=auth_headers(role="admin"),
    )

    response = client.get("/payments/admin/summary", headers=auth_headers(role="admin"))
    assert response.status_code == 200
    data = response.json()
    assert data["total_payments"] == 2
    assert data["confirmed_payments"] == 1
    assert data["failed_payments"] == 1
    assert Decimal(data["total_amount"]) == Decimal("399.80")
    assert Decimal(data["confirmed_amount"]) == Decimal("199.90")
    assert data["payments_by_status"]["confirmed"] == 1
    assert data["payments_by_status"]["failed"] == 1
