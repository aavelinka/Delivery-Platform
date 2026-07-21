from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)
_TRACEPARENT_HEADER = "traceparent"
_TELEMETRY_INIT_LOCK = Lock()
_TELEMETRY_INITIALIZED = False
_TELEMETRY_ENABLED = False
_TRACER_NAME = "delivery-platform"


@dataclass
class TelemetrySpanHandle:
    span: Any
    scope: Any

    @property
    def trace_id(self) -> str:
        return f"{self.span.get_span_context().trace_id:032x}"

    @property
    def span_id(self) -> str:
        return f"{self.span.get_span_context().span_id:016x}"

    @property
    def trace_flags(self) -> str:
        return f"{int(self.span.get_span_context().trace_flags):02x}"

    def set_attributes(self, attributes: Mapping[str, Any] | None) -> None:
        if not attributes:
            return
        for key, value in attributes.items():
            if value is not None:
                self.span.set_attribute(str(key), value)

    def record_exception(self, exc: BaseException) -> None:
        status_module = _import_status_module()
        if status_module is None:
            return
        status, status_code = status_module
        self.span.record_exception(exc)
        self.span.set_status(status(status_code.ERROR, str(exc)))

    def mark_http_status(self, status_code: int) -> None:
        status_module = _import_status_module()
        if status_module is None:
            return
        status, status_enum = status_module
        self.span.set_attribute("http.response.status_code", status_code)
        if status_code >= 500:
            self.span.set_status(status(status_enum.ERROR))

    def end(self) -> None:
        self.scope.__exit__(None, None, None)
        self.span.end()


def configure_telemetry(service_name: str, environment: str | None = None) -> None:
    global _TELEMETRY_ENABLED, _TELEMETRY_INITIALIZED, _TRACER_NAME

    if _TELEMETRY_INITIALIZED:
        return

    with _TELEMETRY_INIT_LOCK:
        if _TELEMETRY_INITIALIZED:
            return

        if not _telemetry_requested():
            _TELEMETRY_INITIALIZED = True
            return

        telemetry_modules = _import_telemetry_modules()
        if telemetry_modules is None:
            _TELEMETRY_INITIALIZED = True
            return

        trace_module, resource_cls, tracer_provider_cls, batch_processor_cls, exporter = (
            telemetry_modules
        )
        resource_attributes = {
            "service.name": service_name,
            "service.namespace": "delivery-platform",
        }
        if environment:
            resource_attributes["deployment.environment"] = environment

        provider = tracer_provider_cls(resource=resource_cls.create(resource_attributes))
        provider.add_span_processor(batch_processor_cls(exporter))
        trace_module.set_tracer_provider(provider)

        _TRACER_NAME = service_name
        _TELEMETRY_ENABLED = True
        _TELEMETRY_INITIALIZED = True
        logger.info(
            "OpenTelemetry tracing enabled",
            extra={
                "service_name": service_name,
                "exporter": "otlp-http"
                if _trace_exporter_endpoint() is not None
                else "console",
            },
        )


def start_telemetry_span(
    *,
    span_name: str,
    traceparent: str | None,
    span_kind: str,
    attributes: Mapping[str, Any] | None = None,
) -> TelemetrySpanHandle | None:
    if not _TELEMETRY_ENABLED:
        return None

    telemetry_runtime = _import_telemetry_runtime()
    if telemetry_runtime is None:
        return None

    trace_module, span_kind_enum, propagator_cls = telemetry_runtime
    context = None
    if traceparent:
        context = propagator_cls().extract(carrier={_TRACEPARENT_HEADER: traceparent})

    tracer = trace_module.get_tracer(_TRACER_NAME)
    span = tracer.start_span(
        span_name,
        context=context,
        kind=_map_span_kind(span_kind_enum, span_kind),
    )
    handle = TelemetrySpanHandle(span=span, scope=trace_module.use_span(span, end_on_exit=False))
    handle.scope.__enter__()
    handle.set_attributes(attributes)
    return handle


def enrich_current_span(attributes: Mapping[str, Any] | None = None) -> None:
    if not _TELEMETRY_ENABLED or not attributes:
        return

    trace_module = _import_trace_module()
    if trace_module is None:
        return

    span = trace_module.get_current_span()
    if span is None:
        return

    for key, value in attributes.items():
        if value is not None:
            span.set_attribute(str(key), value)


def mark_current_span_http_status(status_code: int) -> None:
    if not _TELEMETRY_ENABLED:
        return

    trace_module = _import_trace_module()
    status_module = _import_status_module()
    if trace_module is None or status_module is None:
        return

    status, status_enum = status_module
    span = trace_module.get_current_span()
    if span is None:
        return

    span.set_attribute("http.response.status_code", status_code)
    if status_code >= 500:
        span.set_status(status(status_enum.ERROR))


def telemetry_enabled() -> bool:
    return _TELEMETRY_ENABLED


def _telemetry_requested() -> bool:
    if _env_flag("OTEL_SDK_DISABLED"):
        return False
    return _env_flag("OTEL_ENABLED") or _env_flag("DELIVERY_OTEL_ENABLED")


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _trace_exporter_endpoint() -> str | None:
    return (
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or None
    )


def _trace_exporter_headers() -> dict[str, str] | None:
    headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    if not headers:
        return None

    parsed_headers: dict[str, str] = {}
    for item in headers.split(","):
        key, separator, value = item.partition("=")
        if separator and key.strip():
            parsed_headers[key.strip()] = value.strip()
    return parsed_headers or None


def _trace_exporter_timeout() -> float:
    raw_timeout = os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "10").strip()
    try:
        return float(raw_timeout)
    except ValueError:
        return 10.0


def _import_telemetry_modules() -> tuple[Any, Any, Any, Any, Any] | None:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError as exc:
        logger.warning(
            "OpenTelemetry requested but SDK dependencies are missing: %s",
            exc,
        )
        return None

    endpoint = _trace_exporter_endpoint()
    exporter = (
        OTLPSpanExporter(
            endpoint=endpoint,
            headers=_trace_exporter_headers(),
            timeout=_trace_exporter_timeout(),
        )
        if endpoint
        else ConsoleSpanExporter()
    )
    return trace, Resource, TracerProvider, BatchSpanProcessor, exporter


def _import_telemetry_runtime() -> tuple[Any, Any, Any] | None:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.trace import SpanKind  # type: ignore[import-not-found]
        from opentelemetry.trace.propagation.tracecontext import (  # type: ignore[import-not-found]
            TraceContextTextMapPropagator,
        )
    except ImportError:
        return None
    return trace, SpanKind, TraceContextTextMapPropagator


def _import_trace_module() -> Any | None:
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
    except ImportError:
        return None
    return trace


def _import_status_module() -> tuple[Any, Any] | None:
    try:
        from opentelemetry.trace import Status, StatusCode  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Status, StatusCode


def _map_span_kind(span_kind_enum: Any, value: str) -> Any:
    normalized = value.strip().upper()
    if normalized == "SERVER":
        return span_kind_enum.SERVER
    if normalized == "CONSUMER":
        return span_kind_enum.CONSUMER
    if normalized == "PRODUCER":
        return span_kind_enum.PRODUCER
    if normalized == "CLIENT":
        return span_kind_enum.CLIENT
    return span_kind_enum.INTERNAL
