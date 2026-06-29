from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="USER_", env_file=".env", extra="ignore")

    service_name: str = "user-service"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5436/users"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    gateway_internal_secret: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
