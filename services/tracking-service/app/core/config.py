from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRACKING_", env_file=".env", extra="ignore")

    service_name: str = "tracking-service"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5437/tracking"

    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_client_id: str = "tracking-service"
    kafka_group_id: str = "tracking-service"
    kafka_topic: str = "tracking.events"
    kafka_orders_topic: str = "orders.events"
    kafka_consumer_max_retries: int = 3
    kafka_consumer_retry_backoff_seconds: float = 1.0
    kafka_consumer_dlq_topic: str = "tracking-service.dlq"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    gateway_internal_secret: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
