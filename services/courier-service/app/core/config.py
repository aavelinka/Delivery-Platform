from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COURIER_", env_file=".env", extra="ignore")

    service_name: str = "courier-service"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/couriers"

    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "courier-service"
    kafka_group_id: str = "courier-service"
    kafka_couriers_topic: str = "couriers.events"
    kafka_orders_topic: str = "orders.events"
    kafka_consumer_max_retries: int = 3
    kafka_consumer_retry_backoff_seconds: float = 1.0
    kafka_consumer_dlq_topic: str = "courier-service.dlq"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    gateway_internal_secret: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
