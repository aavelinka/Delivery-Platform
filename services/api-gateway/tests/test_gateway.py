import uuid

import httpx
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.auth import decode_access_token
from app.config import get_settings
from app.main import (
    RATE_LIMIT_BUCKETS,
    _current_user_for_request,
    _enforce_rate_limit,
    _forward_headers,
    _request_id,
    _target_base_url,
    _target_url,
    create_app,
)


def test_decode_access_token(token_factory):
    user_id = uuid.uuid4()
    token = token_factory(user_id, "admin")

    current_user = decode_access_token(get_settings(), f"Bearer {token}")

    assert current_user.id == user_id
    assert current_user.role == "admin"


def test_forward_headers_strips_spoofed_identity(token_factory):
    user_id = uuid.uuid4()
    current_user = decode_access_token(get_settings(), f"Bearer {token_factory(user_id)}")

    headers = _forward_headers(
        source_headers={
            "authorization": "Bearer token",
            "x-user-id": str(uuid.uuid4()),
            "x-gateway-secret": "bad",
        },
        settings=get_settings(),
        current_user=current_user,
        request_id="request-1",
    )

    assert headers["x-user-id"] == str(user_id)
    assert headers["x-gateway-secret"] == "test-gateway-secret"
    assert headers["x-request-id"] == "request-1"
    assert "authorization" not in headers


def test_target_routing():
    settings = get_settings()

    assert _target_base_url(settings, "orders") == settings.order_service_url
    assert _target_base_url(settings, "tracking/orders/1") == settings.tracking_service_url


def test_target_url_preserves_path():
    assert str(_target_url("http://order-service:8000", "/orders/123")) == (
        "http://order-service:8000/orders/123"
    )
    assert str(_target_url("http://gateway-target:8000/api", "/orders/123")) == (
        "http://gateway-target:8000/api/orders/123"
    )


def test_public_auth_path_does_not_require_token():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("testclient", 50000),
    }
    request = Request(scope)

    assert _current_user_for_request(get_settings(), request) is None


def test_options_does_not_require_token():
    scope = {
        "type": "http",
        "method": "OPTIONS",
        "path": "/orders",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("testclient", 50000),
    }
    request = Request(scope)

    assert _current_user_for_request(get_settings(), request) is None


def test_request_id_uses_existing_header():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/orders",
        "headers": [(b"x-request-id", b"existing-id")],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("testclient", 50000),
    }
    request = Request(scope)

    assert _request_id(request) == "existing-id"


def test_rate_limit_blocks_after_limit():
    settings = get_settings()
    old_rate_limit_requests = settings.rate_limit_requests
    old_rate_limit_window_seconds = settings.rate_limit_window_seconds
    settings.rate_limit_requests = 1
    settings.rate_limit_window_seconds = 60
    RATE_LIMIT_BUCKETS.clear()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/orders",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
        "client": ("testclient", 50000),
    }
    request = Request(scope)

    _enforce_rate_limit(settings, request)
    try:
        _enforce_rate_limit(settings, request)
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("Expected rate limit to reject second request")
    finally:
        settings.rate_limit_requests = old_rate_limit_requests
        settings.rate_limit_window_seconds = old_rate_limit_window_seconds
        RATE_LIMIT_BUCKETS.clear()


def test_gateway_returns_request_id_header(monkeypatch, token_factory):
    async def fake_send_with_retries(**kwargs):
        return httpx.Response(
            200,
            json={"status": "ok"},
            headers={"content-type": "application/json"},
            request=httpx.Request(kwargs["method"], kwargs["target_url"]),
        )

    monkeypatch.setattr("app.main._send_with_retries", fake_send_with_retries)

    with TestClient(create_app()) as client:
        response = client.get(
            "/orders",
            headers={
                "authorization": f"Bearer {token_factory(uuid.uuid4())}",
                "x-request-id": "gateway-request-id",
            },
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "gateway-request-id"


def test_metrics_endpoint_exposes_http_metrics():
    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200

        metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "http_requests_total" in metrics_response.text
    assert 'service="api-gateway"' in metrics_response.text
    assert 'path="/health"' in metrics_response.text
