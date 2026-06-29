import asyncio
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Mapping

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status

from app.auth import CurrentUser, decode_access_token
from app.config import Settings, get_settings

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
TRUSTED_IDENTITY_HEADERS = {
    "x-gateway-secret",
    "x-user-id",
    "x-user-email",
    "x-user-role",
}
PUBLIC_AUTH_PATHS = {
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
}
RETRYABLE_METHODS = {"GET", "HEAD", "OPTIONS"}
RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.service_name, version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy(path: str, request: Request) -> Response:
        request_id = _request_id(request)
        _enforce_rate_limit(settings, request)
        target_base_url = _target_base_url(settings, path)
        current_user = _current_user_for_request(settings, request)
        return await _proxy_request(
            settings=settings,
            request=request,
            target_base_url=target_base_url,
            current_user=current_user,
            request_id=request_id,
        )

    return app


app = create_app()


def _target_base_url(settings: Settings, path: str) -> str:
    if path.startswith("auth"):
        return settings.auth_service_url
    if path.startswith("orders"):
        return settings.order_service_url
    if path.startswith("couriers"):
        return settings.courier_service_url
    if path.startswith("notifications"):
        return settings.notification_service_url
    if path.startswith("users"):
        return settings.user_service_url
    if path.startswith("tracking"):
        return settings.tracking_service_url
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")


def _current_user_for_request(settings: Settings, request: Request) -> CurrentUser | None:
    if request.method == "OPTIONS" or request.url.path in PUBLIC_AUTH_PATHS:
        return None
    return decode_access_token(settings, request.headers.get("authorization"))


async def _proxy_request(
    *,
    settings: Settings,
    request: Request,
    target_base_url: str,
    current_user: CurrentUser | None,
    request_id: str,
) -> Response:
    headers = _forward_headers(
        source_headers=request.headers,
        settings=settings,
        current_user=current_user,
        request_id=request_id,
    )
    target_url = _target_url(target_base_url, request.url.path)
    if request.url.query:
        target_url = target_url.copy_with(query=request.url.query.encode("utf-8"))

    body = await request.body()
    try:
        upstream_response = await _send_with_retries(
            settings=settings,
            method=request.method,
            target_url=target_url,
            body=body,
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream service timed out",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream service is unavailable",
        ) from exc

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_response_headers(upstream_response.headers),
        media_type=upstream_response.headers.get("content-type"),
    )


def _forward_headers(
    *,
    source_headers: Mapping[str, str],
    settings: Settings,
    current_user: CurrentUser | None,
    request_id: str,
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in source_headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() not in TRUSTED_IDENTITY_HEADERS
        and key.lower() != "host"
    }
    if current_user is not None:
        headers.pop("authorization", None)
        headers["x-gateway-secret"] = settings.internal_secret
        headers["x-user-id"] = str(current_user.id)
        headers["x-user-role"] = current_user.role.value
        if current_user.email is not None:
            headers["x-user-email"] = current_user.email
    headers["x-request-id"] = request_id
    return headers


async def _send_with_retries(
    *,
    settings: Settings,
    method: str,
    target_url: httpx.URL,
    body: bytes,
    headers: Mapping[str, str],
) -> httpx.Response:
    attempts = max(1, settings.retry_attempts + 1)
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        for attempt in range(attempts):
            try:
                response = await client.request(
                    method,
                    target_url,
                    content=body,
                    headers=headers,
                )
            except httpx.HTTPError:
                if method not in RETRYABLE_METHODS or attempt >= attempts - 1:
                    raise
                await asyncio.sleep(settings.retry_backoff_seconds * (attempt + 1))
                continue
            if not _should_retry(method, response.status_code, attempt, attempts):
                return response
            await asyncio.sleep(settings.retry_backoff_seconds * (attempt + 1))
    return response


def _should_retry(method: str, status_code: int, attempt: int, attempts: int) -> bool:
    return method in RETRYABLE_METHODS and status_code >= 500 and attempt < attempts - 1


def _request_id(request: Request) -> str:
    incoming_request_id = request.headers.get("x-request-id")
    return incoming_request_id if incoming_request_id else str(uuid.uuid4())


def _rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(settings: Settings, request: Request) -> None:
    if settings.rate_limit_requests <= 0:
        return

    now = time.monotonic()
    window_start = now - settings.rate_limit_window_seconds
    bucket = RATE_LIMIT_BUCKETS[_rate_limit_key(request)]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= settings.rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    bucket.append(now)


def _target_url(target_base_url: str, path: str) -> httpx.URL:
    base_url = httpx.URL(target_base_url)
    base_path = base_url.path.rstrip("/")
    normalized_path = f"{base_path}/{path.lstrip('/')}"
    return base_url.copy_with(path=normalized_path)


def _response_headers(source_headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in source_headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "content-length"
    }
