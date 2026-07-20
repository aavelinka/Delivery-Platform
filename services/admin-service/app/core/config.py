from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_", env_file=".env", extra="ignore")

    service_name: str = "admin-service"
    environment: str = "local"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    gateway_internal_secret: str | None = None

    auth_service_url: str = "http://localhost:8003"
    user_service_url: str = "http://localhost:8004"
    order_service_url: str = "http://localhost:8000"
    courier_service_url: str = "http://localhost:8001"
    tracking_service_url: str = "http://localhost:8005"
    notification_service_url: str = "http://localhost:8002"
    payment_service_url: str = "http://localhost:8007"

    request_timeout_seconds: float = 10.0
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
