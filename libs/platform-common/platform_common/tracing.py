import re
import secrets
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

TRACEPARENT_HEADER = "traceparent"
TRACE_METADATA_KEY = "trace"
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_TRACE_FLAGS_RE = re.compile(r"^[0-9a-f]{2}$")
_CURRENT_TRACE_CONTEXT: ContextVar["TraceContext | None"] = ContextVar(
    "delivery_platform_trace_context",
    default=None,
)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    trace_flags: str = "01"

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    def as_metadata(self) -> dict[str, str]:
        metadata = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_flags": self.trace_flags,
            "traceparent": self.traceparent,
        }
        if self.parent_span_id is not None:
            metadata["parent_span_id"] = self.parent_span_id
        return metadata


@contextmanager
def start_trace(traceparent: str | None = None) -> Iterator[TraceContext]:
    parent_context = parse_traceparent(traceparent)
    trace_context = TraceContext(
        trace_id=parent_context.trace_id if parent_context is not None else uuid.uuid4().hex,
        span_id=_new_span_id(),
        parent_span_id=parent_context.span_id if parent_context is not None else None,
        trace_flags=parent_context.trace_flags if parent_context is not None else "01",
    )
    token: Token[TraceContext | None] = _CURRENT_TRACE_CONTEXT.set(trace_context)
    try:
        yield trace_context
    finally:
        _CURRENT_TRACE_CONTEXT.reset(token)


def current_trace_context() -> TraceContext | None:
    return _CURRENT_TRACE_CONTEXT.get()


def get_trace_id() -> str | None:
    trace_context = current_trace_context()
    return trace_context.trace_id if trace_context is not None else None


def get_traceparent() -> str | None:
    trace_context = current_trace_context()
    return trace_context.traceparent if trace_context is not None else None


def inject_trace_metadata(event: dict[str, Any]) -> dict[str, Any]:
    trace_context = current_trace_context()
    if trace_context is None:
        return event

    enriched_event = dict(event)
    metadata = _event_mapping(event.get("metadata"))
    trace_metadata = _event_mapping(metadata.get(TRACE_METADATA_KEY))

    if not trace_metadata:
        trace_metadata = trace_context.as_metadata()
    else:
        trace_metadata.setdefault("trace_id", trace_context.trace_id)
        trace_metadata.setdefault("span_id", trace_context.span_id)
        trace_metadata.setdefault("trace_flags", trace_context.trace_flags)
        trace_metadata.setdefault("traceparent", trace_context.traceparent)
        if trace_context.parent_span_id is not None:
            trace_metadata.setdefault("parent_span_id", trace_context.parent_span_id)

    metadata[TRACE_METADATA_KEY] = trace_metadata
    enriched_event["metadata"] = metadata
    return enriched_event


def traceparent_from_event(event: Mapping[str, Any]) -> str | None:
    trace_metadata = _event_mapping(_event_mapping(event.get("metadata")).get(TRACE_METADATA_KEY))
    traceparent = trace_metadata.get("traceparent")
    if isinstance(traceparent, str) and parse_traceparent(traceparent) is not None:
        return traceparent

    trace_id = trace_metadata.get("trace_id")
    span_id = trace_metadata.get("span_id")
    trace_flags = trace_metadata.get("trace_flags", "01")
    if (
        isinstance(trace_id, str)
        and isinstance(span_id, str)
        and isinstance(trace_flags, str)
        and _is_valid_trace_id(trace_id)
        and _is_valid_span_id(span_id)
        and _is_valid_trace_flags(trace_flags)
    ):
        return f"00-{trace_id}-{span_id}-{trace_flags}"
    return None


def parse_traceparent(traceparent: str | None) -> TraceContext | None:
    if not isinstance(traceparent, str):
        return None

    parts = traceparent.strip().lower().split("-")
    if len(parts) != 4:
        return None

    version, trace_id, span_id, trace_flags = parts
    if version != "00":
        return None
    if not _is_valid_trace_id(trace_id):
        return None
    if not _is_valid_span_id(span_id):
        return None
    if not _is_valid_trace_flags(trace_flags):
        return None

    return TraceContext(trace_id=trace_id, span_id=span_id, trace_flags=trace_flags)


def _event_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _new_span_id() -> str:
    while True:
        span_id = secrets.token_hex(8)
        if span_id != "0" * 16:
            return span_id


def _is_valid_trace_id(trace_id: str) -> bool:
    return bool(_TRACE_ID_RE.fullmatch(trace_id)) and trace_id != "0" * 32


def _is_valid_span_id(span_id: str) -> bool:
    return bool(_SPAN_ID_RE.fullmatch(span_id)) and span_id != "0" * 16


def _is_valid_trace_flags(trace_flags: str) -> bool:
    return bool(_TRACE_FLAGS_RE.fullmatch(trace_flags))
