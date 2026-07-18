from functools import lru_cache

from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    service_name: str = "auth-service"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5435/auth"

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    gateway_internal_secret: str | None = None
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_full_name: str = "Platform Administrator"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("bootstrap_admin_email", "bootstrap_admin_password", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def _validate_bootstrap_admin(self) -> "Settings":
        has_email = self.bootstrap_admin_email is not None
        has_password = self.bootstrap_admin_password is not None
        if has_email != has_password:
            raise ValueError(
                "AUTH_BOOTSTRAP_ADMIN_EMAIL and AUTH_BOOTSTRAP_ADMIN_PASSWORD must be set together"
            )
        return self

    @property
    def jwt_secret_key(self) -> str:
        return self.secret_key

    @property
    def jwt_algorithm(self) -> str:
        return self.algorithm


@lru_cache
def get_settings() -> Settings:
    return Settings()
