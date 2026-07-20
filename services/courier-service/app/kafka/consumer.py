import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from platform_common.tracing import start_trace, traceparent_from_event

from app.core.config import Settings
from app.db.session import SessionLocal
from app.services.courier_service import CourierService

logger = logging.getLogger(__name__)


class OrderEventsConsumer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if not self.settings.kafka_enabled:
            return

        self._consumer = AIOKafkaConsumer(
            self.settings.kafka_orders_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            client_id=f"{self.settings.kafka_client_id}-orders-consumer",
            group_id=self.settings.kafka_group_id,
            enable_auto_commit=False,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        await self._consumer.start()
        self._stopped.clear()
        self._task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def _consume_loop(self) -> None:
        if self._consumer is None:
            return

        while not self._stopped.is_set():
            try:
                message = await self._consumer.getone()
                await self._handle_event(message.value, topic=message.topic)
                await self._consumer.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Failed to handle order event: %s", exc)
                await asyncio.sleep(1)

    async def _handle_event(self, event: dict[str, Any], topic: str | None = None) -> None:
        event_type = str(event.get("event_type") or "unknown")
        with start_trace(
            traceparent_from_event(event),
            span_name=f"kafka consume {event_type}",
            span_kind="consumer",
            attributes={
                "messaging.system": "kafka",
                "messaging.operation": "process",
                "messaging.destination.name": topic or self.settings.kafka_orders_topic,
                "messaging.message.id": event.get("event_id"),
                "messaging.message.conversation_id": event.get("aggregate_id"),
                "messaging.delivery.delivery_platform.event_type": event_type,
            },
        ):
            if event.get("event_type") != "order_created":
                return

            with SessionLocal() as db:
                service = CourierService(db)
                assignment = service.auto_assign_order(event)
                if assignment is None:
                    logger.info("No available courier for order event %s", event.get("event_id"))
                    return

                logger.info("Order event auto-assigned: %s", event.get("event_id"))


class NoopOrderEventsConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
