import json

from aiokafka import AIOKafkaProducer

from app.core.config import Settings


class KafkaPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if not self.settings.kafka_enabled:
            return
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                client_id=self.settings.kafka_client_id,
                value_serializer=lambda value: json.dumps(
                    value,
                    ensure_ascii=False,
                ).encode("utf-8"),
            )
            await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, message: dict[str, object]) -> None:
        if not self.settings.kafka_enabled:
            return
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started")
        await self._producer.send_and_wait(topic, message)


class NoopKafkaPublisher:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic: str, message: dict[str, object]) -> None:
        return None
