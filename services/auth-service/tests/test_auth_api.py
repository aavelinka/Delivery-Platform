import uuid

from app.core.config import get_settings
from app.main import app


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_metrics(client):
    health_response = client.get("/health")
    assert health_response.status_code == 200

    register_response = client.post(
        "/auth/register",
        json={
            "email": "metrics@example.com",
            "password": "strong-password",
            "full_name": "Metrics User",
        },
    )
    assert register_response.status_code == 201

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert 'service="auth-service"' in response.text
    assert 'path="/health"' in response.text
    assert "delivery_auth_users_total" in response.text
    assert "delivery_auth_users_active_total" in response.text
    assert 'delivery_auth_users_by_role{role="customer"} 1.0' in response.text


def test_register_login_me_refresh_and_logout(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "customer@example.com",
            "password": "strong-password",
            "full_name": "Customer One",
        },
    )
    assert register_response.status_code == 201
    tokens = register_response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["user"]["email"] == "customer@example.com"

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "customer@example.com"

    login_response = client.post(
        "/auth/login",
        json={"email": "customer@example.com", "password": "strong-password"},
    )
    assert login_response.status_code == 200

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["refresh_token"] != tokens["refresh_token"]

    reused_refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused_refresh_response.status_code == 401

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout_response.status_code == 204


def test_duplicate_registration_is_rejected(client):
    payload = {
        "email": "customer@example.com",
        "password": "strong-password",
        "full_name": "Customer One",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_bootstrap_admin_can_update_user_role(monkeypatch):
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "super-secure-password")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_FULL_NAME", "Platform Admin")
    get_settings.cache_clear()

    try:
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            admin_login_response = client.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "super-secure-password"},
            )
            assert admin_login_response.status_code == 200
            admin_tokens = admin_login_response.json()
            assert admin_tokens["user"]["role"] == "admin"

            register_response = client.post(
                "/auth/register",
                json={
                    "email": "courier@example.com",
                    "password": "strong-password",
                    "full_name": "Courier Candidate",
                },
            )
            assert register_response.status_code == 201
            user_id = register_response.json()["user"]["id"]

            role_update_response = client.patch(
                f"/auth/users/{user_id}/role",
                json={"role": "courier"},
                headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            )
            assert role_update_response.status_code == 200
            assert role_update_response.json()["role"] == "courier"

            courier_login_response = client.post(
                "/auth/login",
                json={"email": "courier@example.com", "password": "strong-password"},
            )
            assert courier_login_response.status_code == 200
            assert courier_login_response.json()["user"]["role"] == "courier"
    finally:
        get_settings.cache_clear()


def test_non_admin_cannot_update_user_role(client):
    first_user = client.post(
        "/auth/register",
        json={
            "email": "first@example.com",
            "password": "strong-password",
            "full_name": "First User",
        },
    ).json()
    second_user = client.post(
        "/auth/register",
        json={
            "email": "second@example.com",
            "password": "strong-password",
            "full_name": "Second User",
        },
    ).json()

    response = client.patch(
        f"/auth/users/{second_user['user']['id']}/role",
        json={"role": "courier"},
        headers={"Authorization": f"Bearer {first_user['access_token']}"},
    )

    assert response.status_code == 403


def test_gateway_headers_authorize_protected_auth_endpoints(client):
    registered_user = client.post(
        "/auth/register",
        json={
            "email": "gateway-user@example.com",
            "password": "strong-password",
            "full_name": "Gateway User",
        },
    ).json()
    second_user = client.post(
        "/auth/register",
        json={
            "email": "target-user@example.com",
            "password": "strong-password",
            "full_name": "Target User",
        },
    ).json()

    gateway_headers = {
        "x-gateway-secret": "test-gateway-secret",
        "x-user-id": registered_user["user"]["id"],
        "x-user-email": registered_user["user"]["email"],
        "x-user-role": "customer",
    }
    me_response = client.get("/auth/me", headers=gateway_headers)
    assert me_response.status_code == 200
    assert me_response.json()["id"] == registered_user["user"]["id"]

    admin_gateway_headers = {
        "x-gateway-secret": "test-gateway-secret",
        "x-user-id": str(uuid.uuid4()),
        "x-user-email": "admin@example.com",
        "x-user-role": "admin",
    }
    role_update_response = client.patch(
        f"/auth/users/{second_user['user']['id']}/role",
        json={"role": "courier"},
        headers=admin_gateway_headers,
    )
    assert role_update_response.status_code == 200
    assert role_update_response.json()["role"] == "courier"


def test_admin_summary_returns_user_role_counts(client):
    client.post(
        "/auth/register",
        json={
            "email": "first@example.com",
            "password": "strong-password",
            "full_name": "First User",
        },
    ).json()
    second_user = client.post(
        "/auth/register",
        json={
            "email": "second@example.com",
            "password": "strong-password",
            "full_name": "Second User",
        },
    ).json()

    admin_headers = {
        "x-gateway-secret": "test-gateway-secret",
        "x-user-id": str(uuid.uuid4()),
        "x-user-email": "admin@example.com",
        "x-user-role": "admin",
    }
    update_response = client.patch(
        f"/auth/users/{second_user['user']['id']}/role",
        json={"role": "courier"},
        headers=admin_headers,
    )
    assert update_response.status_code == 200

    summary_response = client.get("/auth/admin/summary", headers=admin_headers)

    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_users"] == 2
    assert payload["active_users"] == 2
    assert payload["inactive_users"] == 0
    assert payload["users_by_role"]["customer"] == 1
    assert payload["users_by_role"]["courier"] == 1
