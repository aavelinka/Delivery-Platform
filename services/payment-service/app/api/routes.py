import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    UserRole,
    ensure_self_or_admin,
    require_roles,
)
from app.db.session import get_db
from app.domain.enums import PaymentStatus
from app.schemas.payments import (
    PaymentAdminSummary,
    PaymentConfirm,
    PaymentCreate,
    PaymentEventRead,
    PaymentFail,
    PaymentListResponse,
    PaymentRead,
    PaymentRefund,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


def get_payment_service(db: Session = Depends(get_db)) -> PaymentService:
    return PaymentService(db)


@router.get("/admin/summary", response_model=PaymentAdminSummary)
def admin_summary(
    service: PaymentService = Depends(get_payment_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentAdminSummary:
    return PaymentAdminSummary.model_validate(service.get_admin_summary())


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    service: PaymentService = Depends(get_payment_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.CUSTOMER)),
) -> PaymentRead:
    ensure_self_or_admin(current_user, payload.user_id)
    payment, _event = service.create_payment(payload)
    return PaymentRead.model_validate(payment)


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(
    payment_id: uuid.UUID,
    service: PaymentService = Depends(get_payment_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.CUSTOMER)),
) -> PaymentRead:
    payment = service.get_payment(payment_id)
    if current_user.role == UserRole.CUSTOMER:
        ensure_self_or_admin(current_user, payment.user_id)
    return PaymentRead.model_validate(payment)


@router.get("", response_model=PaymentListResponse)
def list_payments(
    service: PaymentService = Depends(get_payment_service),
    status_filter: PaymentStatus | None = Query(default=None, alias="status"),
    user_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.CUSTOMER)),
) -> PaymentListResponse:
    if current_user.role == UserRole.CUSTOMER:
        user_id = current_user.id

    items, total = service.list_payments(
        status_filter=status_filter,
        user_id=user_id,
        order_id=order_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return PaymentListResponse(
        items=[PaymentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{payment_id}/confirm", response_model=PaymentRead)
def confirm_payment(
    payment_id: uuid.UUID,
    payload: PaymentConfirm,
    service: PaymentService = Depends(get_payment_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentRead:
    payment, _event = service.confirm_payment(payment_id, payload)
    return PaymentRead.model_validate(payment)


@router.post("/{payment_id}/fail", response_model=PaymentRead)
def fail_payment(
    payment_id: uuid.UUID,
    payload: PaymentFail,
    service: PaymentService = Depends(get_payment_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentRead:
    payment, _event = service.fail_payment(payment_id, payload)
    return PaymentRead.model_validate(payment)


@router.post("/{payment_id}/refund", response_model=PaymentRead)
def refund_payment(
    payment_id: uuid.UUID,
    payload: PaymentRefund,
    service: PaymentService = Depends(get_payment_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentRead:
    payment, _event = service.refund_payment(payment_id, payload)
    return PaymentRead.model_validate(payment)


@router.get("/{payment_id}/events", response_model=list[PaymentEventRead])
def list_events(
    payment_id: uuid.UUID,
    service: PaymentService = Depends(get_payment_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.CUSTOMER)),
) -> list[PaymentEventRead]:
    payment = service.get_payment(payment_id)
    if current_user.role == UserRole.CUSTOMER:
        ensure_self_or_admin(current_user, payment.user_id)
    return [PaymentEventRead.model_validate(event) for event in service.list_events(payment_id)]
