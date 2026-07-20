import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

_STRUCTURED_HANDLER_NAME = "delivery-platform-structured-handler"


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().setLevel(logging.INFO)


def install_request_observability(app: FastAPI, service_name: str) -> None:
    logger = _request_logger(service_name)
    registry = CollectorRegistry()
    requests_total = Counter(
        "http_requests_total",
        "Total number of HTTP requests.",
        labelnames=("service", "method", "path", "status_code"),
        registry=registry,
    )
    request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds.",
        labelnames=("service", "method", "path", "status_code"),
        registry=registry,
    )
    app.state.metrics_registry = registry

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.middleware("http")
    async def request_observability_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = get_request_id(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            route_path = _route_path(request)
            status_code_label = str(status_code)
            duration_seconds = time.perf_counter() - started_at
            requests_total.labels(
                service=service_name,
                method=request.method,
                path=route_path,
                status_code=status_code_label,
            ).inc()
            request_duration_seconds.labels(
                service=service_name,
                method=request.method,
                path=route_path,
                status_code=status_code_label,
            ).observe(duration_seconds)
            logger.info(
                json.dumps(
                    _request_log_payload(
                        service_name=service_name,
                        request=request,
                        request_id=request_id,
                        status_code=status_code,
                        duration_ms=duration_seconds * 1000,
                    ),
                    sort_keys=True,
                )
            )


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id

    incoming_request_id = request.headers.get("x-request-id")
    return incoming_request_id if incoming_request_id else str(uuid.uuid4())


def _request_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(f"delivery.http.{service_name}")
    logger.setLevel(logging.INFO)

    if not any(handler.get_name() == _STRUCTURED_HANDLER_NAME for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_STRUCTURED_HANDLER_NAME)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    logger.propagate = False
    return logger


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path_format = getattr(route, "path_format", None)
        if isinstance(path_format, str) and path_format:
            return path_format
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            return path
    return request.url.path


def _request_log_payload(
    *,
    service_name: str,
    request: Request,
    request_id: str,
    status_code: int,
    duration_ms: float,
) -> dict[str, str | int | float]:
    payload: dict[str, str | int | float] = {
        "event": "http_request_completed",
        "service": service_name,
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
    }
    if request.url.query:
        payload["query"] = request.url.query
    if request.client is not None:
        payload["client_ip"] = request.client.host
    return payload
