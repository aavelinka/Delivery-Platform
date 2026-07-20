import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_admin_service
from app.core.auth import CurrentUser, UserRole
from app.core.config import get_settings
from app.main import create_app
from app.services.admin_service import AdminService


class FakeAdminService:
    async def get_overview(self, current_user: CurrentUser, request_id: str):
        assert current_user.role == UserRole.ADMIN
        assert request_id
        return {
            "generated_at": datetime.now(UTC),
            "service_health": [
                {
                    "service": "auth-service",
                    "url": "http://auth-service:8000/health",
                    "ok": True,
                    "status": "ok",
                    "latency_ms": 12.5,
                    "detail": None,
                }
            ],
            "auth": {
                "total_users": 10,
                "active_users": 9,
                "inactive_users": 1,
                "users_by_role": {"customer": 7, "courier": 2, "admin": 1},
            },
            "users": {
                "total_profiles": 8,
                "total_addresses": 12,
                "profiles_with_addresses": 6,
                "default_addresses": 4,
            },
            "orders": {
                "total_orders": 14,
                "orders_with_courier": 10,
                "completed_orders": 5,
                "cancelled_orders": 2,
                "orders_by_status": {"created": 2, "delivered": 5},
            },
            "couriers": {
                "total_couriers": 4,
                "active_couriers": 3,
                "inactive_couriers": 1,
                "couriers_by_availability": {"online": 1, "busy": 2, "offline": 1},
                "assignments_by_status": {"assigned": 2, "delivered": 5},
            },
            "tracking": {
                "tracked_orders": 11,
                "tracked_orders_with_courier": 7,
                "location_updates_total": 30,
                "location_updates_last_24h": 9,
            },
            "notifications": {
                "total_notifications": 16,
                "read_notifications": 6,
                "unread_notifications": 10,
                "notifications_by_status": {"created": 10, "read": 6},
                "notifications_by_channel": {"in_app": 16},
            },
            "payments": {
                "total_payments": 6,
                "pending_payments": 1,
                "confirmed_payments": 3,
                "failed_payments": 1,
                "refunded_payments": 1,
                "total_amount": "890.70",
                "confirmed_amount": "540.30",
                "refunded_amount": "120.40",
                "payments_by_status": {
                    "pending": 1,
                    "confirmed": 3,
                    "failed": 1,
                    "refunded": 1,
                },
            },
        }

    async def get_service_health(self, current_user: CurrentUser, request_id: str):
        assert current_user.role == UserRole.ADMIN
        assert request_id
        return {
            "generated_at": datetime.now(UTC),
            "services": [
                {
                    "service": "auth-service",
                    "url": "http://auth-service:8000/health",
                    "ok": True,
                    "status": "ok",
                    "latency_ms": 10.2,
                    "detail": None,
                }
            ],
        }


def test_health_endpoint():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_admin_overview_requires_admin(token_factory):
    app = create_app()
    app.dependency_overrides[get_admin_service] = lambda: FakeAdminService()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/admin/overview",
                headers={"Authorization": f"Bearer {token_factory(uuid.uuid4(), 'customer')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_overview_returns_aggregated_payload(token_factory):
    app = create_app()
    app.dependency_overrides[get_admin_service] = lambda: FakeAdminService()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/admin/overview",
                headers={"Authorization": f"Bearer {token_factory(uuid.uuid4(), 'admin')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth"]["total_users"] == 10
    assert payload["orders"]["completed_orders"] == 5
    assert payload["notifications"]["unread_notifications"] == 10
    assert payload["payments"]["confirmed_payments"] == 3
    assert payload["service_health"][0]["service"] == "auth-service"


def test_admin_services_health_returns_statuses(token_factory):
    app = create_app()
    app.dependency_overrides[get_admin_service] = lambda: FakeAdminService()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/admin/services/health",
                headers={"Authorization": f"Bearer {token_factory(uuid.uuid4(), 'admin')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["services"][0]["ok"] is True
    assert payload["services"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_service_overview_aggregates_downstream_results(monkeypatch):
    service = AdminService(get_settings())
    current_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
    )

    async def fake_fetch_health(*args, **kwargs):
        del args, kwargs
        return {
            "service": "stub",
            "url": "http://stub/health",
            "ok": True,
            "status": "ok",
            "latency_ms": 1.2,
            "detail": None,
        }

    async def fake_fetch_summary(_client, downstream_service, _headers):
        payloads = {
            "auth-service": {
                "total_users": 1,
                "active_users": 1,
                "inactive_users": 0,
                "users_by_role": {"admin": 1},
            },
            "user-service": {
                "total_profiles": 1,
                "total_addresses": 2,
                "profiles_with_addresses": 1,
                "default_addresses": 1,
            },
            "order-service": {
                "total_orders": 3,
                "orders_with_courier": 2,
                "completed_orders": 1,
                "cancelled_orders": 0,
                "orders_by_status": {"created": 2, "delivered": 1},
            },
            "courier-service": {
                "total_couriers": 2,
                "active_couriers": 2,
                "inactive_couriers": 0,
                "couriers_by_availability": {"online": 1, "busy": 1},
                "assignments_by_status": {"assigned": 1},
            },
            "tracking-service": {
                "tracked_orders": 3,
                "tracked_orders_with_courier": 2,
                "location_updates_total": 7,
                "location_updates_last_24h": 4,
            },
            "notification-service": {
                "total_notifications": 5,
                "read_notifications": 1,
                "unread_notifications": 4,
                "notifications_by_status": {"created": 4, "read": 1},
                "notifications_by_channel": {"in_app": 5},
            },
            "payment-service": {
                "total_payments": 4,
                "pending_payments": 1,
                "confirmed_payments": 2,
                "failed_payments": 1,
                "refunded_payments": 0,
                "total_amount": "799.60",
                "confirmed_amount": "399.80",
                "refunded_amount": "0.00",
                "payments_by_status": {"pending": 1, "confirmed": 2, "failed": 1},
            },
        }
        return downstream_service.name, payloads[downstream_service.name]

    monkeypatch.setattr(service, "_fetch_health", fake_fetch_health)
    monkeypatch.setattr(service, "_fetch_summary", fake_fetch_summary)

    overview = await service.get_overview(current_user, "request-1")

    assert overview["auth"]["users_by_role"]["admin"] == 1
    assert overview["orders"]["total_orders"] == 3
    assert overview["couriers"]["active_couriers"] == 2
    assert overview["payments"]["confirmed_payments"] == 2
    assert len(overview["service_health"]) == 7
