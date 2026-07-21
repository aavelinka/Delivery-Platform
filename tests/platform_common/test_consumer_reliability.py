from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from pathlib import Path
from typing import Any


def _import_platform_common_modules() -> tuple[object, object]:
    repo_root = Path(__file__).resolve().parents[2]
    platform_common_root = repo_root / "libs" / "platform-common"
    platform_common_root_str = str(platform_common_root)
    if platform_common_root_str not in sys.path:
        sys.path.insert(0, platform_common_root_str)

    tracing_module = importlib.import_module("platform_common.tracing")
    reliability_module = importlib.import_module("platform_common.consumer_reliability")
    return tracing_module, reliability_module


tracing, consumer_reliability = _import_platform_common_modules()
build_dead_letter_event = consumer_reliability.build_dead_letter_event
process_message_with_retries = consumer_reliability.process_message_with_retries


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        self.messages.append((topic, message))


def test_process_message_with_retries_publishes_to_dlq_with_trace_metadata() -> None:
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "order_created",
        "aggregate_type": "order",
        "aggregate_id": str(uuid.uuid4()),
        "payload": {"order_id": str(uuid.uuid4())},
        "metadata": {},
    }
    publisher = RecordingPublisher()

    async def always_fail() -> None:
        raise RuntimeError("poison message")

    with tracing.start_trace() as upstream_trace:
        traced_event = tracing.inject_trace_metadata(event)
        should_commit = asyncio.run(
            process_message_with_retries(
                event=traced_event,
                source_service="courier-service",
                consumer_group="courier-service",
                source_topic="orders.events",
                source_partition=2,
                source_offset=15,
                handler=always_fail,
                logger=importlib.import_module("logging").getLogger("test"),
                max_retries=0,
                retry_backoff_seconds=0,
                dlq_topic="courier-service.dlq",
                dlq_publisher=publisher,
            )
        )

    assert should_commit is True
    assert len(publisher.messages) == 1
    topic, dlq_event = publisher.messages[0]
    assert topic == "courier-service.dlq"
    assert dlq_event["event_type"] == "dead_lettered"
    assert dlq_event["payload"]["failed_attempts"] == 1
    assert dlq_event["payload"]["source_partition"] == 2
    assert dlq_event["payload"]["source_offset"] == 15
    assert dlq_event["payload"]["original_event"]["event_id"] == traced_event["event_id"]

    trace_metadata = dlq_event["metadata"]["trace"]
    assert trace_metadata["trace_id"] == upstream_trace.trace_id
    assert trace_metadata["parent_span_id"] != upstream_trace.parent_span_id
    assert trace_metadata["span_id"] != upstream_trace.span_id


def test_build_dead_letter_event_preserves_source_metadata() -> None:
    event = {
        "event_id": "event-1",
        "event_type": "assignment_status_changed",
        "aggregate_type": "assignment",
        "aggregate_id": "assignment-1",
        "payload": {"status": "accepted"},
        "metadata": {"status": "accepted"},
    }

    dead_letter_event = build_dead_letter_event(
        event=event,
        source_service="order-service",
        consumer_group="order-service",
        source_topic="couriers.events",
        source_partition=0,
        source_offset=99,
        failed_attempts=3,
        error=ValueError("invalid transition"),
    )

    assert dead_letter_event["payload"]["error"] == "invalid transition"
    assert dead_letter_event["payload"]["error_type"] == "ValueError"
    assert dead_letter_event["payload"]["original_event"] == event
    assert dead_letter_event["metadata"]["original_event_type"] == "assignment_status_changed"
    assert dead_letter_event["metadata"]["dlq_source_topic"] == "couriers.events"
