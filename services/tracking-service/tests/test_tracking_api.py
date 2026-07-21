import uuid

from sqlalchemy import select

from app.db.models import OutboxEvent
from app.services.tracking_service import TrackingService


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_metrics_expose_tracking_domain_counts(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    TrackingService(db_session).upsert_tracked_order(
        order_id=uuid.UUID(order_id),
        user_id=uuid.UUID(user_id),
        courier_user_id=uuid.UUID(courier_user_id),
    )

    response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(courier_user_id, "courier"),
    )
    assert response.status_code == 201

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "delivery_tracking_orders_total 1.0" in metrics_response.text
    assert "delivery_tracking_orders_with_courier_total 1.0" in metrics_response.text
    assert "delivery_tracking_location_updates_total 1.0" in metrics_response.text


def test_create_and_read_locations(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    headers = auth_headers(courier_user_id, "courier")
    TrackingService(db_session).upsert_tracked_order(
        order_id=uuid.UUID(order_id),
        user_id=uuid.UUID(user_id),
        courier_user_id=uuid.UUID(courier_user_id),
    )

    create_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.9,
            "longitude": 27.5667,
            "accuracy_meters": 12.5,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    location = create_response.json()
    assert location["courier_user_id"] == courier_user_id

    order_response = client.get(
        f"/tracking/orders/{order_id}",
        headers=auth_headers(user_id, "customer"),
    )
    assert order_response.status_code == 200
    assert order_response.json()["id"] == location["id"]

    history_response = client.get(
        f"/tracking/orders/{order_id}/history",
        headers=auth_headers(role="admin"),
    )
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1

    forbidden_response = client.get(
        f"/tracking/orders/{order_id}",
        headers=auth_headers(uuid.uuid4(), "customer"),
    )
    assert forbidden_response.status_code == 403

    courier_response = client.get(f"/tracking/couriers/{courier_user_id}", headers=headers)
    assert courier_response.status_code == 200
    assert courier_response.json()["id"] == location["id"]


def test_create_location_writes_outbox_event(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(courier_user_id, "courier"),
    )

    assert response.status_code == 201
    outbox_event = db_session.scalar(select(OutboxEvent))
    assert outbox_event is not None
    assert outbox_event.status == "pending"
    assert outbox_event.topic == "tracking.events"
    assert outbox_event.payload["event_type"] == "courier_location_updated"


def test_courier_cannot_write_another_courier_location(client, auth_headers):
    response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": str(uuid.uuid4()),
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(uuid.uuid4(), "courier"),
    )
    assert response.status_code == 403


def test_order_location_requires_tracked_order(client, auth_headers):
    courier_user_id = str(uuid.uuid4())
    response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": str(uuid.uuid4()),
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(courier_user_id, "courier"),
    )
    assert response.status_code == 409


def test_order_tracking_owner_cannot_be_changed(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    malicious_user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    headers = auth_headers(courier_user_id, "courier")
    TrackingService(db_session).upsert_tracked_order(
        order_id=uuid.UUID(order_id),
        user_id=uuid.UUID(user_id),
        courier_user_id=uuid.UUID(courier_user_id),
    )

    first_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=headers,
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.91,
            "longitude": 27.57,
        },
        headers=headers,
    )
    assert second_response.status_code == 201
    assert second_response.json()["user_id"] == user_id

    forbidden_response = client.get(
        f"/tracking/orders/{order_id}/history",
        headers=auth_headers(malicious_user_id, "customer"),
    )
    assert forbidden_response.status_code == 403


def test_order_tracking_courier_cannot_be_changed(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    other_courier_user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    TrackingService(db_session).upsert_tracked_order(
        order_id=uuid.UUID(order_id),
        user_id=uuid.uuid4(),
        courier_user_id=uuid.UUID(courier_user_id),
    )

    first_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(courier_user_id, "courier"),
    )
    assert first_response.status_code == 201

    conflict_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": other_courier_user_id,
            "order_id": order_id,
            "latitude": 53.91,
            "longitude": 27.57,
        },
        headers=auth_headers(other_courier_user_id, "courier"),
    )
    assert conflict_response.status_code == 409


def test_admin_summary_returns_tracking_counts(client, auth_headers, db_session):
    courier_user_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())

    TrackingService(db_session).upsert_tracked_order(
        order_id=uuid.UUID(order_id),
        user_id=uuid.UUID(user_id),
        courier_user_id=uuid.UUID(courier_user_id),
    )

    create_response = client.post(
        "/tracking/locations",
        json={
            "courier_user_id": courier_user_id,
            "order_id": order_id,
            "latitude": 53.9,
            "longitude": 27.5667,
        },
        headers=auth_headers(courier_user_id, "courier"),
    )
    assert create_response.status_code == 201

    summary_response = client.get("/tracking/admin/summary", headers=auth_headers(role="admin"))

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["tracked_orders"] == 1
    assert payload["tracked_orders_with_courier"] == 1
    assert payload["location_updates_total"] == 1
    assert payload["location_updates_last_24h"] == 1


def test_admin_kafka_reliability_returns_consumer_settings(client, auth_headers):
    response = client.get(
        "/tracking/admin/kafka/reliability",
        headers=auth_headers(role="admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["consumer_enabled"] is False
    assert payload["consumer_group"] == "tracking-service"
    assert payload["source_topics"] == ["orders.events"]
    assert payload["dlq_topic"] == "tracking-service.dlq"
    assert payload["max_retries"] == 3
