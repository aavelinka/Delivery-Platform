from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any


class DeadLetterEventError(ValueError):
    pass


def summarize_dead_letter_event(event: dict[str, Any]) -> dict[str, Any]:
    dead_letter_event = _validated_dead_letter_event(event)
    payload = _event_object(dead_letter_event.get("payload"))
    metadata = _event_object(dead_letter_event.get("metadata"))
    original_event = _event_object(payload.get("original_event"))

    return {
        "dlq_event_id": dead_letter_event.get("event_id"),
        "source_service": payload.get("source_service") or metadata.get("dlq_source_service"),
        "source_topic": payload.get("source_topic") or metadata.get("dlq_source_topic"),
        "source_partition": payload.get("source_partition"),
        "source_offset": payload.get("source_offset"),
        "failed_attempts": payload.get("failed_attempts"),
        "error": payload.get("error"),
        "error_type": payload.get("error_type"),
        "original_event_id": metadata.get("original_event_id") or original_event.get("event_id"),
        "original_event_type": metadata.get("original_event_type")
        or original_event.get("event_type"),
        "original_aggregate_type": metadata.get("original_aggregate_type")
        or original_event.get("aggregate_type"),
        "original_aggregate_id": metadata.get("original_aggregate_id")
        or original_event.get("aggregate_id"),
        "failed_at": metadata.get("failed_at"),
    }


def build_replay_message(
    dead_letter_event: dict[str, Any],
    *,
    replayed_by: str,
    replay_reason: str | None = None,
) -> tuple[str, dict[str, Any]]:
    event = _validated_dead_letter_event(dead_letter_event)
    payload = _event_object(event.get("payload"))
    source_topic = payload.get("source_topic")
    if not isinstance(source_topic, str) or not source_topic:
        raise DeadLetterEventError("Dead-letter event does not contain a valid source topic")

    original_event = payload.get("original_event")
    if not isinstance(original_event, dict):
        raise DeadLetterEventError("Dead-letter event does not contain an original event payload")

    replay_event = copy.deepcopy(original_event)
    replay_metadata = _event_object(replay_event.get("metadata"))
    original_trace = replay_metadata.pop("trace", None)
    replay_info = _event_object(replay_metadata.get("replay"))
    replay_info.update(
        {
            "replayed_at": datetime.now(UTC).isoformat(),
            "replayed_by": replayed_by,
            "source_dlq_event_id": str(event.get("event_id") or ""),
            "source_dlq_topic": source_topic,
            "failed_attempts": payload.get("failed_attempts"),
        }
    )
    if replay_reason:
        replay_info["reason"] = replay_reason
    if isinstance(original_trace, dict) and original_trace:
        replay_info["original_trace"] = original_trace

    replay_metadata["replay"] = replay_info
    replay_event["metadata"] = replay_metadata
    return source_topic, replay_event


def _validated_dead_letter_event(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("event_type") != "dead_lettered":
        raise DeadLetterEventError("Expected a dead-letter event with event_type='dead_lettered'")
    return event


def _event_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}
