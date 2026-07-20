import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, UserRole, get_current_user, require_roles
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.auth import (
    AuthAdminSummary,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
    UserRoleUpdateRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, settings)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return service.register(payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return service.login(payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    service.logout(payload.refresh_token)


@router.get("/admin/summary", response_model=AuthAdminSummary)
def admin_summary(
    service: AuthService = Depends(get_auth_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> AuthAdminSummary:
    return AuthAdminSummary.model_validate(service.get_admin_summary())


@router.get("/me", response_model=UserRead)
def me(
    current_user: CurrentUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserRead:
    return UserRead.model_validate(service.get_user(current_user.id))


@router.patch("/users/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    service: AuthService = Depends(get_auth_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> UserRead:
    return UserRead.model_validate(service.update_user_role(user_id, payload.role))
