from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _import_platform_common_modules() -> tuple[object, object, object]:
    repo_root = Path(__file__).resolve().parents[2]
    platform_common_root = repo_root / "libs" / "platform-common"
    platform_common_root_str = str(platform_common_root)
    if platform_common_root_str not in sys.path:
        sys.path.insert(0, platform_common_root_str)

    telemetry_module = importlib.import_module("platform_common.telemetry")
    tracing_module = importlib.import_module("platform_common.tracing")
    observability_module = importlib.import_module("platform_common.observability")
    return telemetry_module, tracing_module, observability_module


telemetry, tracing, observability = _import_platform_common_modules()
install_request_observability = observability.install_request_observability


class FakeTelemetrySpan:
    def __init__(
        self,
        *,
        trace_id: str = "1" * 32,
        span_id: str = "2" * 16,
        trace_flags: str = "01",
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.trace_flags = trace_flags
        self.recorded_exception: BaseException | None = None
        self.ended = False

    def record_exception(self, exc: BaseException) -> None:
        self.recorded_exception = exc

    def end(self) -> None:
        self.ended = True


def test_start_trace_uses_telemetry_span_context(monkeypatch: pytest.MonkeyPatch) -> None:
    span = FakeTelemetrySpan()
    incoming_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    monkeypatch.setattr(tracing, "_start_telemetry_span", lambda **_: span)

    with tracing.start_trace(
        incoming_traceparent,
        span_name="GET /health",
        span_kind="server",
    ) as trace_context:
        assert trace_context.trace_id == span.trace_id
        assert trace_context.span_id == span.span_id
        assert trace_context.parent_span_id == "00f067aa0ba902b7"
        assert tracing.get_traceparent() == trace_context.traceparent

    assert span.ended is True


def test_start_trace_records_exception_on_telemetry_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    span = FakeTelemetrySpan()
    monkeypatch.setattr(tracing, "_start_telemetry_span", lambda **_: span)

    with pytest.raises(RuntimeError, match="boom"):
        with tracing.start_trace(span_name="broken-operation"):
            raise RuntimeError("boom")

    assert isinstance(span.recorded_exception, RuntimeError)
    assert span.ended is True


def test_install_request_observability_tolerates_missing_otel_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_TELEMETRY_INITIALIZED", False)
    monkeypatch.setattr(telemetry, "_TELEMETRY_ENABLED", False)
    monkeypatch.setattr(telemetry, "_import_telemetry_modules", lambda: None)

    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    install_request_observability(app, "test-service", "test")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-trace-id"]
    assert response.headers["traceparent"]
