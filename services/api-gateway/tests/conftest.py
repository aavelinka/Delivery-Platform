import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

TEST_SECRET = "test-secret"
TEST_GATEWAY_SECRET = "test-gateway-secret"

os.environ["GATEWAY_JWT_SECRET_KEY"] = TEST_SECRET
os.environ["GATEWAY_INTERNAL_SECRET"] = TEST_GATEWAY_SECRET


def make_token(user_id: uuid.UUID | str, role: str = "customer") -> str:
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
def token_factory():
    return make_token
