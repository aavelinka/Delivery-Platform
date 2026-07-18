import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from test_support.postgres import (  # noqa: E402
    configure_postgres_test_environment,
    reset_database,
    teardown_database,
)

configure_postgres_test_environment(
    database_env_var="AUTH_DATABASE_URL",
    default_database_url="postgresql+psycopg://postgres:postgres@localhost:5435/auth_test",
    extra_env={
        "AUTH_SECRET_KEY": "test-secret",
        "AUTH_GATEWAY_INTERNAL_SECRET": "test-gateway-secret",
        "AUTH_CORS_ORIGINS": '["*"]',
    },
)

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
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
