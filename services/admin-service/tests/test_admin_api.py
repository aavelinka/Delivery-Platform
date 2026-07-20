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

    async def get_analytics(self, current_user: CurrentUser, request_id: str):
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
                    "latency_ms": 10.2,
                    "detail": None,
                }
            ],
            "health": {
                "total_services": 7,
                "healthy_services": 7,
                "degraded_services": 0,
                "average_latency_ms": 10.2,
                "slowest_service": "auth-service",
            },
            "activity": {
                "total_users": 10,
                "total_profiles": 8,
                "total_orders": 14,
                "orders_without_courier": 4,
                "active_couriers": 3,
                "tracked_orders": 11,
                "total_payments": 6,
                "total_notifications": 16,
                "unread_notifications": 10,
                "location_updates_last_24h": 9,
            },
            "financials": {
                "total_amount": "890.70",
                "confirmed_amount": "540.30",
                "refunded_amount": "120.40",
                "average_payment_value": "148.45",
                "average_confirmed_payment_value": "180.10",
            },
            "conversion": {
                "profile_coverage_pct": 75.0,
                "courier_assignment_pct": 71.43,
                "courier_activity_pct": 75.0,
                "tracking_coverage_pct": 78.57,
                "order_completion_pct": 35.71,
                "order_cancellation_pct": 14.29,
                "payment_confirmation_pct": 50.0,
                "payment_failure_pct": 16.67,
                "refund_rate_pct": 16.67,
                "notification_read_pct": 37.5,
            },
            "alerts": [
                {
                    "code": "orders_waiting_courier",
                    "severity": "warning",
                    "message": "4 orders do not have a courier yet",
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


def test_admin_analytics_returns_business_metrics(token_factory):
    app = create_app()
    app.dependency_overrides[get_admin_service] = lambda: FakeAdminService()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/admin/analytics",
                headers={"Authorization": f"Bearer {token_factory(uuid.uuid4(), 'admin')}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["healthy_services"] == 7
    assert payload["activity"]["orders_without_courier"] == 4
    assert payload["conversion"]["payment_confirmation_pct"] == 50.0
    assert payload["alerts"][0]["code"] == "orders_waiting_courier"


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


@pytest.mark.asyncio
async def test_admin_service_analytics_derives_business_metrics(monkeypatch):
    service = AdminService(get_settings())
    current_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
    )

    async def fake_fetch_health(_client, downstream_service):
        return {
            "service": downstream_service.name,
            "url": f"{downstream_service.base_url}/health",
            "ok": downstream_service.name != "tracking-service",
            "status": "ok" if downstream_service.name != "tracking-service" else "unavailable",
            "latency_ms": 5.0 if downstream_service.name != "payment-service" else 12.0,
            "detail": None,
        }

    async def fake_fetch_summary(_client, downstream_service, _headers):
        payloads = {
            "auth-service": {
                "total_users": 12,
                "active_users": 11,
                "inactive_users": 1,
                "users_by_role": {"customer": 9, "courier": 2, "admin": 1},
            },
            "user-service": {
                "total_profiles": 10,
                "total_addresses": 15,
                "profiles_with_addresses": 8,
                "default_addresses": 6,
            },
            "order-service": {
                "total_orders": 10,
                "orders_with_courier": 7,
                "completed_orders": 4,
                "cancelled_orders": 1,
                "orders_by_status": {"created": 2, "in_delivery": 3, "delivered": 4},
            },
            "courier-service": {
                "total_couriers": 5,
                "active_couriers": 4,
                "inactive_couriers": 1,
                "couriers_by_availability": {"online": 2, "busy": 2, "offline": 1},
                "assignments_by_status": {"assigned": 2, "accepted": 1, "delivered": 4},
            },
            "tracking-service": {
                "tracked_orders": 8,
                "tracked_orders_with_courier": 6,
                "location_updates_total": 20,
                "location_updates_last_24h": 7,
            },
            "notification-service": {
                "total_notifications": 18,
                "read_notifications": 6,
                "unread_notifications": 12,
                "notifications_by_status": {"created": 12, "read": 6},
                "notifications_by_channel": {"in_app": 18},
            },
            "payment-service": {
                "total_payments": 8,
                "pending_payments": 1,
                "confirmed_payments": 4,
                "failed_payments": 2,
                "refunded_payments": 1,
                "total_amount": "1200.00",
                "confirmed_amount": "640.00",
                "refunded_amount": "80.00",
                "payments_by_status": {
                    "pending": 1,
                    "confirmed": 4,
                    "failed": 2,
                    "refunded": 1,
                },
            },
        }
        return downstream_service.name, payloads[downstream_service.name]

    monkeypatch.setattr(service, "_fetch_health", fake_fetch_health)
    monkeypatch.setattr(service, "_fetch_summary", fake_fetch_summary)

    analytics = await service.get_analytics(current_user, "request-2")

    assert analytics["health"]["healthy_services"] == 6
    assert analytics["health"]["degraded_services"] == 1
    assert analytics["health"]["slowest_service"] == "payment-service"
    assert analytics["activity"]["orders_without_courier"] == 3
    assert str(analytics["financials"]["average_payment_value"]) == "150.00"
    assert str(analytics["financials"]["average_confirmed_payment_value"]) == "160.00"
    assert analytics["conversion"]["courier_assignment_pct"] == 70.0
    assert analytics["conversion"]["payment_failure_pct"] == 25.0
    alert_codes = {alert["code"] for alert in analytics["alerts"]}
    assert "services_degraded" in alert_codes
    assert "orders_waiting_courier" in alert_codes
    assert "tracking_gap" in alert_codes
    assert "payment_failures_high" in alert_codes
    assert "notifications_unread_backlog" in alert_codes
