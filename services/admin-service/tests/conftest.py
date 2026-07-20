import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jose import jwt

TEST_SECRET = "test-secret"
TEST_GATEWAY_SECRET = "test-gateway-secret"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_LIB_ROOT = REPO_ROOT / "libs" / "platform-common"

for path in (REPO_ROOT, SHARED_LIB_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

os.environ["ADMIN_JWT_SECRET_KEY"] = TEST_SECRET
os.environ["ADMIN_GATEWAY_INTERNAL_SECRET"] = TEST_GATEWAY_SECRET


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
def token_factory():
    return make_token
