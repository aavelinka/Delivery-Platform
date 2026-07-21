from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from platform_common.tracing import inject_trace_metadata, start_trace, traceparent_from_event


class DeadLetterPublisher(Protocol):
    async def publish(self, topic: str, message: dict[str, Any]) -> None: ...


async def process_message_with_retries(
    *,
    event: dict[str, Any],
    source_service: str,
    consumer_group: str,
    source_topic: str,
    source_partition: int | None,
    source_offset: int | None,
    handler: Callable[[], Awaitable[None]],
    logger: logging.Logger,
    max_retries: int,
    retry_backoff_seconds: float,
    dlq_topic: str | None,
    dlq_publisher: DeadLetterPublisher | None,
) -> bool:
    total_attempts = max(1, max_retries + 1)
    last_error: Exception | None = None

    for attempt in range(1, total_attempts + 1):
        try:
            await handler()
        except Exception as exc:
            last_error = exc
            if attempt < total_attempts:
                logger.warning(
                    "Retrying Kafka message after failure",
                    extra={
                        "service": source_service,
                        "consumer_group": consumer_group,
                        "topic": source_topic,
                        "partition": source_partition,
                        "offset": source_offset,
                        "event_id": event.get("event_id"),
                        "event_type": event.get("event_type"),
                        "attempt": attempt,
                        "max_attempts": total_attempts,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(retry_backoff_seconds * attempt)
                continue

            if not dlq_topic or dlq_publisher is None:
                raise

            await publish_dead_letter(
                event=event,
                source_service=source_service,
                consumer_group=consumer_group,
                source_topic=source_topic,
                source_partition=source_partition,
                source_offset=source_offset,
                failed_attempts=attempt,
                error=exc,
                dlq_topic=dlq_topic,
                dlq_publisher=dlq_publisher,
            )
            logger.error(
                "Kafka message moved to DLQ",
                extra={
                    "service": source_service,
                    "consumer_group": consumer_group,
                    "topic": source_topic,
                    "partition": source_partition,
                    "offset": source_offset,
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "failed_attempts": attempt,
                    "dlq_topic": dlq_topic,
                    "error": str(exc),
                },
            )
            return True
        else:
            if attempt > 1:
                logger.info(
                    "Kafka message processed after retry",
                    extra={
                        "service": source_service,
                        "consumer_group": consumer_group,
                        "topic": source_topic,
                        "partition": source_partition,
                        "offset": source_offset,
                        "event_id": event.get("event_id"),
                        "event_type": event.get("event_type"),
                        "attempt": attempt,
                    },
                )
            return True

    if last_error is not None:
        raise last_error
    return True


async def publish_dead_letter(
    *,
    event: dict[str, Any],
    source_service: str,
    consumer_group: str,
    source_topic: str,
    source_partition: int | None,
    source_offset: int | None,
    failed_attempts: int,
    error: Exception,
    dlq_topic: str,
    dlq_publisher: DeadLetterPublisher,
) -> None:
    event_type = str(event.get("event_type") or "unknown")
    with start_trace(
        traceparent_from_event(event),
        span_name=f"kafka dlq {event_type}",
        span_kind="producer",
        attributes={
            "messaging.system": "kafka",
            "messaging.operation": "publish",
            "messaging.destination.name": dlq_topic,
            "messaging.message.id": event.get("event_id"),
            "messaging.message.conversation_id": event.get("aggregate_id"),
            "messaging.delivery.delivery_platform.event_type": event_type,
            "messaging.delivery.delivery_platform.dlq": True,
        },
    ):
        await dlq_publisher.publish(
            dlq_topic,
            build_dead_letter_event(
                event=event,
                source_service=source_service,
                consumer_group=consumer_group,
                source_topic=source_topic,
                source_partition=source_partition,
                source_offset=source_offset,
                failed_attempts=failed_attempts,
                error=error,
            ),
        )


def build_dead_letter_event(
    *,
    event: dict[str, Any],
    source_service: str,
    consumer_group: str,
    source_topic: str,
    source_partition: int | None,
    source_offset: int | None,
    failed_attempts: int,
    error: Exception,
) -> dict[str, Any]:
    original_event_id = str(event.get("event_id") or uuid.uuid4())
    aggregate_id = str(event.get("aggregate_id") or original_event_id)
    dead_letter_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "dead_lettered",
        "aggregate_type": "dead_letter",
        "aggregate_id": aggregate_id,
        "payload": {
            "source_service": source_service,
            "consumer_group": consumer_group,
            "source_topic": source_topic,
            "source_partition": source_partition,
            "source_offset": source_offset,
            "failed_attempts": failed_attempts,
            "error": str(error),
            "error_type": type(error).__name__,
            "original_event": event,
        },
        "metadata": {
            "failed_at": datetime.now(UTC).isoformat(),
            "original_event_id": original_event_id,
            "original_event_type": str(event.get("event_type") or "unknown"),
            "original_aggregate_type": str(event.get("aggregate_type") or "unknown"),
            "original_aggregate_id": aggregate_id,
            "dlq_source_service": source_service,
            "dlq_source_topic": source_topic,
        },
    }
    return inject_trace_metadata(dead_letter_event)
