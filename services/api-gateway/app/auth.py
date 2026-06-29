import uuid
from enum import StrEnum
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.config import Settings


class UserRole(StrEnum):
    CUSTOMER = "customer"
    COURIER = "courier"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: EmailStr | None = None
    role: UserRole


def decode_access_token(settings: Settings, authorization: str | None) -> CurrentUser:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token type",
        )

    try:
        user_id = uuid.UUID(str(payload["sub"]))
        role = UserRole(str(payload["role"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token claims",
        ) from exc

    email = payload.get("email")
    return CurrentUser(id=user_id, email=str(email) if email else None, role=role)
