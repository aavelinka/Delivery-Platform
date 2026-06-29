import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    UserRole,
    ensure_self_or_admin,
    get_current_user,
    require_roles,
)
from app.db.session import get_db
from app.schemas.notifications import (
    NotificationCreate,
    NotificationListResponse,
    NotificationRead,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate,
    service: NotificationService = Depends(get_notification_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationRead:
    notification = service.create_notification(payload)
    return NotificationRead.model_validate(notification)


@router.get("/users/{user_id}", response_model=NotificationListResponse)
def list_user_notifications(
    user_id: uuid.UUID,
    service: NotificationService = Depends(get_notification_service),
    unread_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationListResponse:
    ensure_self_or_admin(current_user, user_id)
    items, total = service.list_user_notifications(
        user_id=user_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[NotificationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(
    notification_id: uuid.UUID,
    service: NotificationService = Depends(get_notification_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationRead:
    notification = service.get_notification(notification_id)
    ensure_self_or_admin(current_user, notification.user_id)
    return NotificationRead.model_validate(notification)


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_as_read(
    notification_id: uuid.UUID,
    service: NotificationService = Depends(get_notification_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationRead:
    existing_notification = service.get_notification(notification_id)
    ensure_self_or_admin(current_user, existing_notification.user_id)
    notification = service.mark_as_read(notification_id)
    return NotificationRead.model_validate(notification)
