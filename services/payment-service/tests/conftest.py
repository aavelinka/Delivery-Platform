import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt

TEST_SECRET = "test-secret"
REPO_ROOT = Path(__file__).resolve().parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from test_support.postgres import (  # noqa: E402
    configure_postgres_test_environment,
    reset_database,
    teardown_database,
)

configure_postgres_test_environment(
    database_env_var="PAYMENT_DATABASE_URL",
    default_database_url="postgresql+psycopg://postgres:postgres@localhost:5439/payments_test",
    extra_env={
        "PAYMENT_KAFKA_ENABLED": "false",
        "PAYMENT_JWT_SECRET_KEY": TEST_SECRET,
        "PAYMENT_CORS_ORIGINS": '["*"]',
    },
)

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    reset_database(engine, Base.metadata)
    yield
    teardown_database(engine, Base.metadata)


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    with SessionLocal() as db:
        yield db


def make_token(user_id: uuid.UUID | str, role: str = "admin") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": f"{role}@example.com",
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture()
def auth_headers():
    def build(user_id: uuid.UUID | str | None = None, role: str = "admin") -> dict[str, str]:
        token = make_token(user_id or uuid.uuid4(), role)
        return {"Authorization": f"Bearer {token}"}

    return build
