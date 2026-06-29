import uuid

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
from app.domain.enums import AssignmentStatus
from app.schemas.couriers import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentRead,
    AssignmentStatusUpdate,
    CourierAvailabilityUpdate,
    CourierCreate,
    CourierListResponse,
    CourierRead,
    CourierUpdate,
)
from app.services.courier_service import CourierService

router = APIRouter(prefix="/couriers", tags=["couriers"])


def get_courier_service(db: Session = Depends(get_db)) -> CourierService:
    return CourierService(db)


@router.post("", response_model=CourierRead, status_code=status.HTTP_201_CREATED)
def create_courier(
    payload: CourierCreate,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> CourierRead:
    if current_user.role == UserRole.COURIER:
        ensure_self_or_admin(current_user, payload.user_id)
    courier = service.create_courier(payload)
    return CourierRead.model_validate(courier)


@router.get("/available", response_model=CourierListResponse)
def list_available_couriers(
    service: CourierService = Depends(get_courier_service),
    city: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
) -> CourierListResponse:
    items, total = service.list_available_couriers(city=city, limit=limit, offset=offset)
    return CourierListResponse(
        items=[CourierRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{courier_id}", response_model=CourierRead)
def get_courier(
    courier_id: uuid.UUID,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> CourierRead:
    courier = service.get_courier(courier_id)
    if current_user.role == UserRole.COURIER:
        ensure_self_or_admin(current_user, courier.user_id)
    elif current_user.role == UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return CourierRead.model_validate(courier)


@router.patch("/{courier_id}", response_model=CourierRead)
def update_courier(
    courier_id: uuid.UUID,
    payload: CourierUpdate,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> CourierRead:
    existing_courier = service.get_courier(courier_id)
    if current_user.role == UserRole.COURIER:
        ensure_self_or_admin(current_user, existing_courier.user_id)
    courier = service.update_courier(courier_id, payload)
    return CourierRead.model_validate(courier)


@router.patch("/{courier_id}/availability", response_model=CourierRead)
def change_availability(
    courier_id: uuid.UUID,
    payload: CourierAvailabilityUpdate,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> CourierRead:
    existing_courier = service.get_courier(courier_id)
    if current_user.role == UserRole.COURIER:
        ensure_self_or_admin(current_user, existing_courier.user_id)
    courier = service.change_availability(courier_id, payload)
    return CourierRead.model_validate(courier)


@router.post("/assignments", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def assign_courier(
    payload: AssignmentCreate,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> AssignmentRead:
    assignment = service.assign_courier(payload)
    return AssignmentRead.model_validate(assignment)


@router.patch("/assignments/{assignment_id}/status", response_model=AssignmentRead)
def update_assignment_status(
    assignment_id: uuid.UUID,
    payload: AssignmentStatusUpdate,
    service: CourierService = Depends(get_courier_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> AssignmentRead:
    existing_assignment = service.get_assignment(assignment_id)
    if current_user.role == UserRole.COURIER:
        courier = service.get_courier(existing_assignment.courier_id)
        ensure_self_or_admin(current_user, courier.user_id)
    assignment = service.update_assignment_status(assignment_id, payload)
    return AssignmentRead.model_validate(assignment)


@router.get("/{courier_id}/assignments", response_model=AssignmentListResponse)
def list_assignments(
    courier_id: uuid.UUID,
    service: CourierService = Depends(get_courier_service),
    order_id: uuid.UUID | None = None,
    status_filter: AssignmentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> AssignmentListResponse:
    courier = service.get_courier(courier_id)
    if current_user.role == UserRole.COURIER:
        ensure_self_or_admin(current_user, courier.user_id)
    items, total = service.list_assignments(
        courier_id=courier_id,
        order_id=order_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return AssignmentListResponse(
        items=[AssignmentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
