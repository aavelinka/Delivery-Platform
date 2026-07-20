import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, Protocol

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt  # type: ignore[import-untyped]
from pydantic import BaseModel, EmailStr


class AuthSettings(Protocol):
    jwt_secret_key: str
    jwt_algorithm: str
    gateway_internal_secret: str | None


class UserRole(StrEnum):
    CUSTOMER = "customer"
    COURIER = "courier"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: EmailStr | None = None
    role: UserRole


def build_get_current_user(get_settings: Callable[[], AuthSettings]):
    def get_current_user(
        authorization: Annotated[str | None, Header()] = None,
        x_gateway_secret: Annotated[str | None, Header()] = None,
        x_user_id: Annotated[str | None, Header()] = None,
        x_user_email: Annotated[str | None, Header()] = None,
        x_user_role: Annotated[str | None, Header()] = None,
        settings: AuthSettings = Depends(get_settings),
    ) -> CurrentUser:
        gateway_user = current_user_from_gateway_headers(
            settings=settings,
            x_gateway_secret=x_gateway_secret,
            x_user_id=x_user_id,
            x_user_email=x_user_email,
            x_user_role=x_user_role,
        )
        if gateway_user is not None:
            return gateway_user

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

    return get_current_user


def build_require_roles(get_current_user):
    def require_roles(*roles: UserRole):
        def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
            if current_user.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            return current_user

        return dependency

    return require_roles


def current_user_from_gateway_headers(
    *,
    settings: AuthSettings,
    x_gateway_secret: str | None,
    x_user_id: str | None,
    x_user_email: str | None,
    x_user_role: str | None,
) -> CurrentUser | None:
    if x_gateway_secret is None and x_user_id is None and x_user_role is None:
        return None
    if settings.gateway_internal_secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gateway auth is not configured",
        )
    if x_gateway_secret != settings.gateway_internal_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway credentials",
        )
    try:
        user_id = uuid.UUID(str(x_user_id))
        role = UserRole(str(x_user_role))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway user headers",
        ) from exc
    return CurrentUser(id=user_id, email=x_user_email, role=role)


def ensure_self_or_admin(current_user: CurrentUser, user_id: uuid.UUID | None) -> None:
    if current_user.role == UserRole.ADMIN:
        return
    if user_id is not None and current_user.id == user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )
