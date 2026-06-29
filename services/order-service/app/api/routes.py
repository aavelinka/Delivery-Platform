import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    UserRole,
    ensure_self_or_admin,
    get_current_user,
    require_roles,
)
from app.db.session import get_db
from app.domain.enums import OrderStatus
from app.schemas.orders import (
    OrderCancel,
    OrderCreate,
    OrderEventRead,
    OrderListResponse,
    OrderRead,
    OrderStatusUpdate,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    service: OrderService = Depends(get_order_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrderRead:
    ensure_self_or_admin(current_user, payload.user_id)
    order, _event = service.create_order(payload)
    return OrderRead.model_validate(order)


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: uuid.UUID,
    service: OrderService = Depends(get_order_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrderRead:
    order = service.get_order(order_id)
    if current_user.role == UserRole.COURIER and order.courier_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    if current_user.role == UserRole.CUSTOMER:
        ensure_self_or_admin(current_user, order.user_id)
    return OrderRead.model_validate(order)


@router.get("", response_model=OrderListResponse)
def list_orders(
    service: OrderService = Depends(get_order_service),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    user_id: uuid.UUID | None = None,
    courier_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrderListResponse:
    if current_user.role == UserRole.CUSTOMER:
        user_id = current_user.id
    elif current_user.role == UserRole.COURIER:
        courier_user_id = current_user.id

    items, total = service.list_orders(
        status_filter=status_filter,
        user_id=user_id,
        courier_id=courier_user_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    return OrderListResponse(
        items=[OrderRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{order_id}/status", response_model=OrderRead)
def change_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    service: OrderService = Depends(get_order_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> OrderRead:
    if current_user.role == UserRole.COURIER:
        existing_order = service.get_order(order_id)
        if existing_order.courier_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
    order, _event = service.change_status(order_id, payload)
    return OrderRead.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderRead)
def cancel_order(
    order_id: uuid.UUID,
    payload: OrderCancel,
    service: OrderService = Depends(get_order_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> OrderRead:
    existing_order = service.get_order(order_id)
    if current_user.role == UserRole.CUSTOMER:
        ensure_self_or_admin(current_user, existing_order.user_id)
    elif current_user.role == UserRole.COURIER and existing_order.courier_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    order, _event = service.cancel_order(order_id, payload)
    return OrderRead.model_validate(order)


@router.get("/{order_id}/events", response_model=list[OrderEventRead])
def list_events(
    order_id: uuid.UUID,
    service: OrderService = Depends(get_order_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[OrderEventRead]:
    order = service.get_order(order_id)
    if current_user.role == UserRole.CUSTOMER:
        ensure_self_or_admin(current_user, order.user_id)
    elif current_user.role == UserRole.COURIER and order.courier_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return [OrderEventRead.model_validate(event) for event in service.list_events(order_id)]
