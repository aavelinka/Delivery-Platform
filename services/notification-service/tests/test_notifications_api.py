import uuid

from app.services.notification_service import NotificationService


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_create_get_list_and_read_notification(client, auth_headers):
    user_id = str(uuid.uuid4())
    admin_headers = auth_headers(role="admin")
    user_headers = auth_headers(user_id, "customer")
    create_response = client.post(
        "/notifications",
        json={
            "user_id": user_id,
            "channel": "in_app",
            "title": "Order created",
            "message": "Order was created.",
            "payload": {"order_id": str(uuid.uuid4())},
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    notification = create_response.json()
    assert notification["status"] == "created"

    get_response = client.get(f"/notifications/{notification['id']}", headers=user_headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == notification["id"]

    list_response = client.get(f"/notifications/users/{user_id}", headers=user_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    read_response = client.patch(f"/notifications/{notification['id']}/read", headers=user_headers)
    assert read_response.status_code == 200
    assert read_response.json()["status"] == "read"
    assert read_response.json()["read_at"] is not None


def test_create_notification_from_order_event(db_session):
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    notification = service.create_from_event(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "order_created",
            "aggregate_type": "order",
            "aggregate_id": order_id,
            "payload": {
                "order_id": order_id,
                "user_id": user_id,
            },
            "metadata": {
                "order_id": order_id,
                "user_id": user_id,
                "status": "created",
            },
        }
    )

    assert notification is not None
    assert str(notification.user_id) == user_id
    assert notification.source_event_type == "order_created"


def test_create_notification_from_courier_event_uses_courier_user_id(db_session):
    courier_user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    notification = service.create_from_event(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "courier_assigned",
            "aggregate_type": "assignment",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {
                "order_id": order_id,
            },
            "metadata": {
                "order_id": order_id,
                "courier_user_id": courier_user_id,
                "status": "assigned",
            },
        }
    )

    assert notification is not None
    assert str(notification.user_id) == courier_user_id
    assert notification.source_event_type == "courier_assigned"
    assert notification.title == "Courier assigned"


def test_event_processing_is_idempotent(db_session):
    event_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    service = NotificationService(db_session)
    event = {
        "event_id": event_id,
        "event_type": "order_created",
        "aggregate_type": "order",
        "aggregate_id": order_id,
        "payload": {
            "order_id": order_id,
            "user_id": user_id,
        },
        "metadata": {
            "order_id": order_id,
            "user_id": user_id,
            "status": "created",
        },
    }

    first = service.create_from_event(event)
    second = service.create_from_event(event)

    assert first is not None
    assert second is not None
    assert first.id == second.id


def test_tracking_event_does_not_create_notification(db_session):
    user_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    service = NotificationService(db_session)

    notification = service.create_from_event(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "courier_location_updated",
            "aggregate_type": "courier",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {
                "order_id": order_id,
                "user_id": user_id,
                "courier_user_id": str(uuid.uuid4()),
            },
            "metadata": {
                "order_id": order_id,
                "user_id": user_id,
            },
        }
    )

    assert notification is None


def test_courier_event_without_recipient_does_not_create_notification(db_session):
    service = NotificationService(db_session)

    notification = service.create_from_event(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "assignment_status_changed",
            "aggregate_type": "assignment",
            "aggregate_id": str(uuid.uuid4()),
            "payload": {
                "order_id": str(uuid.uuid4()),
            },
            "metadata": {
                "order_id": str(uuid.uuid4()),
                "status": "accepted",
            },
        }
    )

    assert notification is None


def test_admin_summary_returns_notification_counts(client, auth_headers):
    user_id = str(uuid.uuid4())
    admin_headers = auth_headers(role="admin")
    user_headers = auth_headers(user_id, "customer")

    create_response = client.post(
        "/notifications",
        json={
            "user_id": user_id,
            "channel": "in_app",
            "title": "Order created",
            "message": "Order was created.",
            "payload": {"order_id": str(uuid.uuid4())},
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    notification_id = create_response.json()["id"]

    read_response = client.patch(f"/notifications/{notification_id}/read", headers=user_headers)
    assert read_response.status_code == 200

    summary_response = client.get("/notifications/admin/summary", headers=admin_headers)

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_notifications"] == 1
    assert payload["read_notifications"] == 1
    assert payload["unread_notifications"] == 0
    assert payload["notifications_by_status"]["read"] == 1
    assert payload["notifications_by_channel"]["in_app"] == 1
