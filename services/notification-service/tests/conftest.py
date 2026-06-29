import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt

TEST_DB = Path(__file__).resolve().parent / "notification_service_test.db"
TEST_SECRET = "test-secret"

os.environ["NOTIFICATION_DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["NOTIFICATION_KAFKA_ENABLED"] = "false"
os.environ["NOTIFICATION_JWT_SECRET_KEY"] = TEST_SECRET
os.environ["NOTIFICATION_CORS_ORIGINS"] = '["*"]'

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _setup_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if TEST_DB.exists():
        TEST_DB.unlink()


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
