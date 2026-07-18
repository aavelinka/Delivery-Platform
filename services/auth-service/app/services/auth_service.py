import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.domain.enums import UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def register(self, data: RegisterRequest) -> TokenResponse:
        email = data.email.lower()
        existing_user = self.db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        user = User(
            email=email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._issue_tokens(user)

    def ensure_bootstrap_admin(self) -> User | None:
        email = self.settings.bootstrap_admin_email
        password = self.settings.bootstrap_admin_password
        if email is None or password is None:
            return None

        normalized_email = str(email).lower()
        user = self.db.scalar(select(User).where(User.email == normalized_email))
        should_commit = False

        if user is None:
            user = User(
                email=normalized_email,
                hashed_password=hash_password(password),
                full_name=self.settings.bootstrap_admin_full_name,
                role=UserRole.ADMIN,
                is_active=True,
            )
            self.db.add(user)
            should_commit = True
        else:
            if user.role != UserRole.ADMIN:
                user.role = UserRole.ADMIN
                should_commit = True
            if not user.is_active:
                user.is_active = True
                should_commit = True
            if not user.full_name and self.settings.bootstrap_admin_full_name:
                user.full_name = self.settings.bootstrap_admin_full_name
                should_commit = True

        if should_commit:
            self.db.commit()
            self.db.refresh(user)

        return user

    def login(self, data: LoginRequest) -> TokenResponse:
        user = self.db.scalar(select(User).where(User.email == data.email.lower()))
        if user is None or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive",
            )
        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        token_hash = hash_token(refresh_token)
        token_record = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if token_record is None or token_record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        if _normalize_utc(token_record.expires_at) <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        token_record.revoked_at = datetime.now(UTC)
        self.db.commit()
        return self._issue_tokens(token_record.user)

    def logout(self, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        token_record = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if token_record is not None and token_record.revoked_at is None:
            token_record.revoked_at = datetime.now(UTC)
            self.db.commit()

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
        return user

    def update_user_role(self, user_id: uuid.UUID, role: UserRole) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user.role != role:
            user.role = role
            self.db.commit()
            self.db.refresh(user)
        return user

    def _issue_tokens(self, user: User) -> TokenResponse:
        refresh_token = generate_refresh_token()
        refresh_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=self.settings.refresh_token_expire_days),
        )
        self.db.add(refresh_record)
        self.db.commit()
        self.db.refresh(user)

        access_token = create_access_token(
            settings=self.settings,
            user_id=user.id,
            email=user.email,
            role=user.role,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
            user=UserRead.model_validate(user),
        )
