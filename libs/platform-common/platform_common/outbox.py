import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session
from platform_common.tracing import inject_trace_metadata

logger = logging.getLogger(__name__)


class KafkaPublisher(Protocol):
    async def publish(self, topic: str, message: dict[str, Any]) -> None: ...


class OutboxEventModel(Protocol):
    id: Any
    topic: str
    payload: dict[str, Any]
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    published_at: datetime | None


def add_outbox_event(
    db: Session,
    event_model: type[Any],
    *,
    topic: str,
    payload: dict[str, Any],
) -> OutboxEventModel:
    event = event_model(topic=topic, payload=inject_trace_metadata(payload))
    db.add(event)
    return event


class OutboxPublisher:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        event_model: type[Any],
        publisher: KafkaPublisher,
        batch_size: int = 50,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.session_factory = session_factory
        self.event_model = event_model
        self.publisher = publisher
        self.batch_size = batch_size
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        self._stopped.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._publish_batch()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Outbox publisher failed: %s", exc)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _publish_batch(self) -> None:
        with self.session_factory() as db:
            events = list(
                db.scalars(
                    select(self.event_model)
                    .where(self.event_model.status == "pending")
                    .order_by(self.event_model.created_at)
                    .limit(self.batch_size)
                ).all()
            )
            for event in events:
                try:
                    await self.publisher.publish(event.topic, event.payload)
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = str(exc)
                    logger.exception("Failed to publish outbox event %s: %s", event.id, exc)
                else:
                    event.status = "published"
                    event.published_at = datetime.now(UTC)
                    event.last_error = None
                db.commit()
