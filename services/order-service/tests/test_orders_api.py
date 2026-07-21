import uuid

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.services.order_service import OrderService


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_metrics_expose_order_domain_counts(client, auth_headers):
    user_id = str(uuid.uuid4())
    response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=auth_headers(user_id, "customer"),
    )
    assert response.status_code == 201

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "delivery_orders_total 1.0" in metrics_response.text
    assert "delivery_orders_with_courier_total 0.0" in metrics_response.text
    assert 'delivery_orders_by_status{status="created"} 1.0' in metrics_response.text


def test_create_get_and_list_order(client, auth_headers):
    user_id = str(uuid.uuid4())
    payload = {
        "user_id": user_id,
        "pickup_address": "Warehouse A",
        "delivery_address": "Main street 12",
        "total_price": "149.90",
        "comment": "Call on arrival",
    }

    headers = auth_headers(user_id, "customer")
    create_response = client.post("/orders", json=payload, headers=headers)
    assert create_response.status_code == 201
    order = create_response.json()
    assert order["user_id"] == user_id
    assert order["status"] == "created"

    order_id = order["id"]

    get_response = client.get(f"/orders/{order_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == order_id

    list_response = client.get("/orders", headers=headers)
    assert list_response.status_code == 200
    data = list_response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == order_id


def test_create_order_writes_outbox_event(client, db_session, auth_headers):
    user_id = str(uuid.uuid4())
    response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=auth_headers(user_id, "customer"),
    )

    assert response.status_code == 201
    outbox_event = db_session.scalar(select(OutboxEvent))
    assert outbox_event is not None
    assert outbox_event.status == "pending"
    assert outbox_event.topic == "orders.events"
    assert outbox_event.payload["event_type"] == "order_created"


def test_order_status_flow(client, auth_headers):
    user_id = str(uuid.uuid4())
    courier_user_id = str(uuid.uuid4())
    admin_headers = auth_headers(role="admin")
    create_response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=admin_headers,
    )
    order_id = create_response.json()["id"]

    waiting_response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "waiting_for_courier"},
        headers=admin_headers,
    )
    assert waiting_response.status_code == 200
    assert waiting_response.json()["status"] == "waiting_for_courier"

    assign_response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "courier_assigned", "courier_user_id": courier_user_id},
        headers=admin_headers,
    )
    assert assign_response.status_code == 200
    assert assign_response.json()["courier_user_id"] == courier_user_id

    delivery_response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "in_delivery"},
        headers=admin_headers,
    )
    assert delivery_response.status_code == 200
    assert delivery_response.json()["status"] == "in_delivery"

    completed_response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "delivered"},
        headers=admin_headers,
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["status"] == "delivered"


def test_cancel_order(client, auth_headers):
    user_id = str(uuid.uuid4())
    headers = auth_headers(user_id, "customer")
    create_response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=headers,
    )
    order_id = create_response.json()["id"]

    cancel_response = client.post(
        f"/orders/{order_id}/cancel",
        json={"reason": "Customer request", "changed_by": "customer"},
        headers=headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    events_response = client.get(f"/orders/{order_id}/events", headers=headers)
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "order_created"
    assert events[1]["event_type"] == "order_cancelled"


def test_invalid_status_transition_is_rejected(client, auth_headers):
    user_id = str(uuid.uuid4())
    admin_headers = auth_headers(role="admin")
    create_response = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=admin_headers,
    )
    order_id = create_response.json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "delivered"},
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_apply_courier_assigned_event(client, db_session, auth_headers):
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
    order_id = create_response.json()["id"]
    courier_profile_id = str(uuid.uuid4())
    courier_user_id = str(uuid.uuid4())

    service = OrderService(db_session)
    result = service.apply_courier_assigned(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "courier_assigned",
            "aggregate_type": "assignment",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {
                "assignment_id": str(uuid.uuid4()),
                "order_id": order_id,
                "courier_id": courier_profile_id,
                "courier_user_id": courier_user_id,
            },
            "metadata": {
                "order_id": order_id,
                "courier_id": courier_profile_id,
                "courier_user_id": courier_user_id,
                "status": "assigned",
            },
        }
    )

    assert result is not None
    order, event = result
    assert str(order.courier_id) == courier_user_id
    assert order.status == "courier_assigned"
    assert event.event_type == "courier_assigned"


def test_apply_assignment_status_changed_event(client, db_session, auth_headers):
    user_id = str(uuid.uuid4())
    courier_user_id = str(uuid.uuid4())
    order_id = client.post(
        "/orders",
        json={
            "user_id": user_id,
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=auth_headers(user_id, "customer"),
    ).json()["id"]

    service = OrderService(db_session)
    assigned = service.apply_courier_assigned(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "courier_assigned",
            "payload": {
                "assignment_id": str(uuid.uuid4()),
                "order_id": order_id,
                "courier_user_id": courier_user_id,
            },
            "metadata": {
                "order_id": order_id,
                "courier_user_id": courier_user_id,
            },
        }
    )
    assert assigned is not None

    in_delivery = service.apply_assignment_status_changed(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "assignment_status_changed",
            "payload": {
                "assignment_id": str(uuid.uuid4()),
                "order_id": order_id,
                "courier_user_id": courier_user_id,
                "status": "picked_up",
            },
            "metadata": {
                "order_id": order_id,
                "courier_user_id": courier_user_id,
                "status": "picked_up",
            },
        }
    )
    assert in_delivery is not None
    assert in_delivery[0].status == "in_delivery"

    delivered = service.apply_assignment_status_changed(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "assignment_status_changed",
            "payload": {
                "assignment_id": str(uuid.uuid4()),
                "order_id": order_id,
                "courier_user_id": courier_user_id,
                "status": "delivered",
            },
            "metadata": {
                "order_id": order_id,
                "courier_user_id": courier_user_id,
                "status": "delivered",
            },
        }
    )
    assert delivered is not None
    assert delivered[0].status == "delivered"


def test_admin_summary_returns_order_counts(client, auth_headers):
    admin_headers = auth_headers(role="admin")
    first_order = client.post(
        "/orders",
        json={
            "user_id": str(uuid.uuid4()),
            "pickup_address": "Warehouse A",
            "delivery_address": "Main street 12",
            "total_price": "149.90",
        },
        headers=admin_headers,
    )
    assert first_order.status_code == 201

    second_order = client.post(
        "/orders",
        json={
            "user_id": str(uuid.uuid4()),
            "pickup_address": "Warehouse B",
            "delivery_address": "Main street 13",
            "total_price": "99.90",
        },
        headers=admin_headers,
    )
    assert second_order.status_code == 201

    cancel_response = client.post(
        f"/orders/{second_order.json()['id']}/cancel",
        json={"reason": "Customer request"},
        headers=admin_headers,
    )
    assert cancel_response.status_code == 200

    summary_response = client.get("/orders/admin/summary", headers=admin_headers)

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_orders"] == 2
    assert payload["cancelled_orders"] == 1
    assert payload["orders_by_status"]["created"] == 1
    assert payload["orders_by_status"]["cancelled"] == 1


def test_admin_kafka_reliability_returns_consumer_settings(client, auth_headers):
    response = client.get("/orders/admin/kafka/reliability", headers=auth_headers(role="admin"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["consumer_enabled"] is False
    assert payload["consumer_group"] == "order-service"
    assert payload["source_topics"] == ["couriers.events"]
    assert payload["dlq_topic"] == "order-service.dlq"
    assert payload["max_retries"] == 3
