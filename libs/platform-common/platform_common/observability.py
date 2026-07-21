import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from platform_common.telemetry import (
    configure_telemetry,
    enrich_current_span,
    mark_current_span_http_status,
)
from platform_common.tracing import TRACEPARENT_HEADER, TraceContext, start_trace

_STRUCTURED_HANDLER_NAME = "delivery-platform-structured-handler"
_METRICS_LOGGER_NAME = "delivery.metrics"

SummaryScalar = bool | int | float | Decimal
SummaryMetricValue = SummaryScalar | Mapping[str, SummaryScalar]
SummaryLoader = Callable[[], Mapping[str, SummaryMetricValue]]


@dataclass(frozen=True)
class SummaryMetricDefinition:
    name: str
    description: str
    summary_key: str
    label_name: str | None = None


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().setLevel(logging.INFO)


def install_request_observability(
    app: FastAPI,
    service_name: str,
    environment: str | None = None,
) -> None:
    configure_telemetry(service_name, environment)
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
        trace_attributes = {
            "http.request.method": request.method,
            "url.path": request.url.path,
        }
        with start_trace(
            request.headers.get(TRACEPARENT_HEADER),
            span_name=f"{request.method} {request.url.path}",
            span_kind="server",
            attributes=trace_attributes,
        ) as trace_context:
            request.state.request_id = request_id
            request.state.trace_id = trace_context.trace_id
            request.state.traceparent = trace_context.traceparent
            started_at = time.perf_counter()
            response: Response | None = None
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers["x-request-id"] = request_id
                response.headers["x-trace-id"] = trace_context.trace_id
                response.headers[TRACEPARENT_HEADER] = trace_context.traceparent
                return response
            finally:
                route_path = _route_path(request)
                status_code_label = str(status_code)
                duration_seconds = time.perf_counter() - started_at
                enrich_current_span(
                    {
                        "http.route": route_path,
                        "http.response.status_code": status_code,
                        "http.request.duration_ms": round(duration_seconds * 1000, 2),
                    }
                )
                mark_current_span_http_status(status_code)
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
                            trace_context=trace_context,
                            status_code=status_code,
                            duration_ms=duration_seconds * 1000,
                        ),
                        sort_keys=True,
                    )
                )


def register_metrics_collector(app: FastAPI, collector: object) -> None:
    registry = getattr(app.state, "metrics_registry", None)
    if not isinstance(registry, CollectorRegistry):
        raise RuntimeError("Metrics registry is not configured on the FastAPI app")
    registry.register(collector)


def register_summary_metrics(
    app: FastAPI,
    *,
    load_summary: SummaryLoader,
    metrics: Sequence[SummaryMetricDefinition],
    logger_name: str = _METRICS_LOGGER_NAME,
) -> None:
    register_metrics_collector(
        app,
        _SummaryMetricsCollector(
            load_summary=load_summary,
            metrics=metrics,
            logger=logging.getLogger(logger_name),
        ),
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
    trace_context: TraceContext,
    status_code: int,
    duration_ms: float,
) -> dict[str, str | int | float]:
    payload: dict[str, str | int | float] = {
        "event": "http_request_completed",
        "service": service_name,
        "request_id": request_id,
        "trace_id": trace_context.trace_id,
        "span_id": trace_context.span_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
    }
    if trace_context.parent_span_id is not None:
        payload["parent_span_id"] = trace_context.parent_span_id
    if request.url.query:
        payload["query"] = request.url.query
    if request.client is not None:
        payload["client_ip"] = request.client.host
    return payload


class _SummaryMetricsCollector:
    def __init__(
        self,
        *,
        load_summary: SummaryLoader,
        metrics: Sequence[SummaryMetricDefinition],
        logger: logging.Logger,
    ) -> None:
        self._load_summary = load_summary
        self._metrics = tuple(metrics)
        self._logger = logger

    def collect(self) -> list[GaugeMetricFamily]:
        try:
            summary = dict(self._load_summary())
        except Exception:
            self._logger.exception("Failed to load summary metrics")
            return []

        metric_families: list[GaugeMetricFamily] = []
        for metric in self._metrics:
            family = self._metric_family(metric, summary)
            if family is not None:
                metric_families.append(family)
        return metric_families

    def _metric_family(
        self,
        metric: SummaryMetricDefinition,
        summary: Mapping[str, SummaryMetricValue],
    ) -> GaugeMetricFamily | None:
        raw_value = summary.get(metric.summary_key)
        if metric.label_name is None:
            family = GaugeMetricFamily(metric.name, metric.description)
            family.add_metric([], _metric_value(raw_value))
            return family

        family = GaugeMetricFamily(metric.name, metric.description, labels=[metric.label_name])
        if raw_value is None:
            return family
        if not isinstance(raw_value, Mapping):
            self._logger.warning(
                "Summary metric %s expected a mapping for key %s, got %s",
                metric.name,
                metric.summary_key,
                type(raw_value).__name__,
            )
            return family

        for label_value, item_value in sorted(raw_value.items(), key=lambda item: str(item[0])):
            family.add_metric([str(label_value)], _metric_value(item_value))
        return family


def _metric_value(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    raise TypeError(f"Unsupported summary metric value type: {type(value).__name__}")
