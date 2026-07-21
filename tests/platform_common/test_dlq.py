from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest


def _import_platform_common_module() -> object:
    repo_root = Path(__file__).resolve().parents[2]
    platform_common_root = repo_root / "libs" / "platform-common"
    platform_common_root_str = str(platform_common_root)
    if platform_common_root_str not in sys.path:
        sys.path.insert(0, platform_common_root_str)

    return importlib.import_module("platform_common.dlq")


dlq = _import_platform_common_module()
DeadLetterEventError = dlq.DeadLetterEventError
build_replay_message = dlq.build_replay_message
summarize_dead_letter_event = dlq.summarize_dead_letter_event


def _dead_letter_event() -> dict[str, object]:
    return {
        "event_id": "dlq-event-1",
        "event_type": "dead_lettered",
        "aggregate_type": "dead_letter",
        "aggregate_id": "order-1",
        "payload": {
            "source_service": "courier-service",
            "consumer_group": "courier-service",
            "source_topic": "orders.events",
            "source_partition": 2,
            "source_offset": 18,
            "failed_attempts": 3,
            "error": "poison message",
            "error_type": "RuntimeError",
            "original_event": {
                "event_id": "order-event-1",
                "event_type": "order_created",
                "aggregate_type": "order",
                "aggregate_id": "order-1",
                "payload": {"order_id": "order-1"},
                "metadata": {
                    "request_id": "req-1",
                    "trace": {
                        "trace_id": "1" * 32,
                        "span_id": "2" * 16,
                        "parent_span_id": "3" * 16,
                        "traceparent": "00-11111111111111111111111111111111-2222222222222222-01",
                    },
                },
            },
        },
        "metadata": {
            "failed_at": "2026-07-21T12:00:00+00:00",
            "original_event_id": "order-event-1",
            "original_event_type": "order_created",
            "original_aggregate_type": "order",
            "original_aggregate_id": "order-1",
            "dlq_source_service": "courier-service",
            "dlq_source_topic": "orders.events",
        },
    }


def test_summarize_dead_letter_event_returns_operator_friendly_view() -> None:
    summary = summarize_dead_letter_event(_dead_letter_event())

    assert summary == {
        "dlq_event_id": "dlq-event-1",
        "source_service": "courier-service",
        "source_topic": "orders.events",
        "source_partition": 2,
        "source_offset": 18,
        "failed_attempts": 3,
        "error": "poison message",
        "error_type": "RuntimeError",
        "original_event_id": "order-event-1",
        "original_event_type": "order_created",
        "original_aggregate_type": "order",
        "original_aggregate_id": "order-1",
        "failed_at": "2026-07-21T12:00:00+00:00",
    }


def test_build_replay_message_enriches_replay_metadata_and_returns_source_topic() -> None:
    dead_letter_event = _dead_letter_event()

    target_topic, replay_event = build_replay_message(
        dead_letter_event,
        replayed_by="test-operator",
        replay_reason="fixed downstream mapping",
    )

    assert target_topic == "orders.events"
    assert replay_event["event_id"] == "order-event-1"
    assert replay_event["metadata"]["request_id"] == "req-1"
    assert "trace" not in replay_event["metadata"]

    replay_metadata = replay_event["metadata"]["replay"]
    assert replay_metadata["replayed_by"] == "test-operator"
    assert replay_metadata["reason"] == "fixed downstream mapping"
    assert replay_metadata["source_dlq_event_id"] == "dlq-event-1"
    assert replay_metadata["source_dlq_topic"] == "orders.events"
    assert replay_metadata["failed_attempts"] == 3
    assert replay_metadata["original_trace"]["trace_id"] == "1" * 32
    assert datetime.fromisoformat(replay_metadata["replayed_at"])

    original_trace = dead_letter_event["payload"]["original_event"]["metadata"]["trace"]
    assert original_trace["span_id"] == "2" * 16


def test_build_replay_message_rejects_non_dlq_event() -> None:
    with pytest.raises(DeadLetterEventError, match="event_type='dead_lettered'"):
        build_replay_message(
            {"event_type": "order_created"},
            replayed_by="test-operator",
        )
