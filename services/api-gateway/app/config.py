from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    environment: str = "local"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    internal_secret: str

    auth_service_url: str = "http://localhost:8003"
    order_service_url: str = "http://localhost:8000"
    courier_service_url: str = "http://localhost:8001"
    notification_service_url: str = "http://localhost:8002"
    user_service_url: str = "http://localhost:8004"
    tracking_service_url: str = "http://localhost:8005"
    admin_service_url: str = "http://localhost:8006"
    payment_service_url: str = "http://localhost:8007"

    request_timeout_seconds: float = 30.0
    retry_attempts: int = 2
    retry_backoff_seconds: float = 0.2
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
