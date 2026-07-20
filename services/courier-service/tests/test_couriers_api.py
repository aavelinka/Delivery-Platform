import uuid

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.services.courier_service import CourierService


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_create_get_and_list_available_courier(client, auth_headers):
    user_id = str(uuid.uuid4())
    headers = auth_headers(user_id, "courier")
    payload = {
        "user_id": user_id,
        "full_name": "Alex Smith",
        "phone": "+375291112233",
        "vehicle_type": "bike",
        "city": "Minsk",
        "notes": "Night shifts",
    }

    create_response = client.post("/couriers", json=payload, headers=headers)
    assert create_response.status_code == 201
    courier = create_response.json()
    assert courier["user_id"] == user_id
    assert courier["availability"] == "offline"

    courier_id = courier["id"]

    get_response = client.get(f"/couriers/{courier_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == courier_id

    available_response = client.get("/couriers/available", headers=headers)
    assert available_response.status_code == 200
    assert available_response.json()["total"] == 0

    online_response = client.patch(
        f"/couriers/{courier_id}/availability",
        json={"availability": "online", "changed_by": "dispatcher"},
        headers=headers,
    )
    assert online_response.status_code == 200
    assert online_response.json()["availability"] == "online"

    available_response = client.get("/couriers/available", headers=headers)
    assert available_response.status_code == 200
    assert available_response.json()["total"] == 1


def test_create_courier_writes_outbox_event(client, db_session, auth_headers):
    user_id = str(uuid.uuid4())
    response = client.post(
        "/couriers",
        json={
            "user_id": user_id,
            "full_name": "Alex Smith",
            "city": "Minsk",
        },
        headers=auth_headers(user_id, "courier"),
    )

    assert response.status_code == 201
    outbox_event = db_session.scalar(select(OutboxEvent))
    assert outbox_event is not None
    assert outbox_event.status == "pending"
    assert outbox_event.topic == "couriers.events"
    assert outbox_event.payload["event_type"] == "courier_created"


def test_assignment_flow(client, auth_headers):
    admin_headers = auth_headers(role="admin")
    courier_create = client.post(
        "/couriers",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Alex Smith",
            "phone": "+375291112233",
            "vehicle_type": "bike",
            "city": "Minsk",
        },
        headers=admin_headers,
    )
    courier_id = courier_create.json()["id"]

    client.patch(
        f"/couriers/{courier_id}/availability",
        json={"availability": "online"},
        headers=admin_headers,
    )

    assignment_create = client.post(
        "/couriers/assignments",
        json={
            "courier_id": courier_id,
            "order_id": str(uuid.uuid4()),
            "payload": {"order_type": "food"},
        },
        headers=admin_headers,
    )
    assert assignment_create.status_code == 201
    assignment = assignment_create.json()
    assert assignment["status"] == "assigned"

    courier_after_assignment = client.get(f"/couriers/{courier_id}", headers=admin_headers).json()
    assert courier_after_assignment["availability"] == "busy"

    accepted = client.patch(
        f"/couriers/assignments/{assignment['id']}/status",
        json={"status": "accepted", "changed_by": "courier"},
        headers=admin_headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    picked_up = client.patch(
        f"/couriers/assignments/{assignment['id']}/status",
        json={"status": "picked_up", "changed_by": "courier"},
        headers=admin_headers,
    )
    assert picked_up.status_code == 200
    assert picked_up.json()["status"] == "picked_up"

    delivered = client.patch(
        f"/couriers/assignments/{assignment['id']}/status",
        json={"status": "delivered", "changed_by": "courier"},
        headers=admin_headers,
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"

    courier_after_delivery = client.get(f"/couriers/{courier_id}", headers=admin_headers).json()
    assert courier_after_delivery["availability"] == "online"


def test_invalid_assignment_transition_is_rejected(client, auth_headers):
    admin_headers = auth_headers(role="admin")
    courier_create = client.post(
        "/couriers",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Alex Smith",
            "city": "Minsk",
        },
        headers=admin_headers,
    )
    courier_id = courier_create.json()["id"]

    client.patch(
        f"/couriers/{courier_id}/availability",
        json={"availability": "online"},
        headers=admin_headers,
    )
    assignment_create = client.post(
        "/couriers/assignments",
        json={
            "courier_id": courier_id,
            "order_id": str(uuid.uuid4()),
            "payload": {},
        },
        headers=admin_headers,
    )
    assignment_id = assignment_create.json()["id"]

    response = client.patch(
        f"/couriers/assignments/{assignment_id}/status",
        json={"status": "delivered"},
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_auto_assign_order_event(client, db_session, auth_headers):
    admin_headers = auth_headers(role="admin")
    courier_create = client.post(
        "/couriers",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Alex Smith",
            "city": "Minsk",
        },
        headers=admin_headers,
    )
    courier_id = courier_create.json()["id"]
    client.patch(
        f"/couriers/{courier_id}/availability",
        json={"availability": "online"},
        headers=admin_headers,
    )

    order_id = str(uuid.uuid4())
    service = CourierService(db_session)
    assignment = service.auto_assign_order(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "order_created",
            "aggregate_type": "order",
            "aggregate_id": order_id,
            "payload": {
                "order_id": order_id,
                "user_id": str(uuid.uuid4()),
                "delivery_city": "Minsk",
            },
            "metadata": {"status": "created"},
        }
    )

    assert assignment is not None
    assert str(assignment.courier_id) == courier_id
    assert str(assignment.order_id) == order_id


def test_admin_summary_returns_courier_and_assignment_counts(client, auth_headers):
    admin_headers = auth_headers(role="admin")
    courier_response = client.post(
        "/couriers",
        json={
            "user_id": str(uuid.uuid4()),
            "full_name": "Alex Smith",
            "city": "Minsk",
        },
        headers=admin_headers,
    )
    assert courier_response.status_code == 201
    courier_id = courier_response.json()["id"]

    online_response = client.patch(
        f"/couriers/{courier_id}/availability",
        json={"availability": "online"},
        headers=admin_headers,
    )
    assert online_response.status_code == 200

    assignment_response = client.post(
        "/couriers/assignments",
        json={
            "courier_id": courier_id,
            "order_id": str(uuid.uuid4()),
            "payload": {},
        },
        headers=admin_headers,
    )
    assert assignment_response.status_code == 201

    summary_response = client.get("/couriers/admin/summary", headers=admin_headers)

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_couriers"] == 1
    assert payload["active_couriers"] == 1
    assert payload["couriers_by_availability"]["busy"] == 1
    assert payload["assignments_by_status"]["assigned"] == 1
