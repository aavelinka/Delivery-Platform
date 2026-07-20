import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, UserRole, get_current_user, require_roles
from app.db.models import CourierLocation
from app.db.session import get_db
from app.schemas.tracking import LocationCreate, LocationRead, TrackingAdminSummary
from app.services.tracking_service import TrackingService

router = APIRouter(prefix="/tracking", tags=["tracking"])


def get_tracking_service(db: Session = Depends(get_db)) -> TrackingService:
    return TrackingService(db)


@router.get("/admin/summary", response_model=TrackingAdminSummary)
def admin_summary(
    service: TrackingService = Depends(get_tracking_service),
    _current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
) -> TrackingAdminSummary:
    return TrackingAdminSummary.model_validate(service.get_admin_summary())


def ensure_location_access(current_user: CurrentUser, location: CourierLocation) -> None:
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.role == UserRole.COURIER and current_user.id == location.courier_user_id:
        return
    if current_user.role == UserRole.CUSTOMER and current_user.id == location.user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    service: TrackingService = Depends(get_tracking_service),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN, UserRole.COURIER)),
) -> LocationRead:
    if current_user.role == UserRole.COURIER and current_user.id != payload.courier_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    location = service.create_location(payload)
    return LocationRead.model_validate(location)


@router.get("/orders/{order_id}", response_model=LocationRead)
def get_order_location(
    order_id: uuid.UUID,
    service: TrackingService = Depends(get_tracking_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> LocationRead:
    location = service.get_current_for_order(order_id)
    ensure_location_access(current_user, location)
    return LocationRead.model_validate(location)


@router.get("/orders/{order_id}/history", response_model=list[LocationRead])
def get_order_history(
    order_id: uuid.UUID,
    service: TrackingService = Depends(get_tracking_service),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[LocationRead]:
    items, current_location = service.list_order_history(
        order_id=order_id,
        limit=limit,
        offset=offset,
    )
    ensure_location_access(current_user, current_location)
    if current_user.role != UserRole.ADMIN:
        items = [
            item
            for item in items
            if item.user_id == current_location.user_id
            and item.courier_user_id == current_location.courier_user_id
        ]
    return [LocationRead.model_validate(item) for item in items]


@router.get("/couriers/{courier_user_id}", response_model=LocationRead)
def get_courier_location(
    courier_user_id: uuid.UUID,
    service: TrackingService = Depends(get_tracking_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> LocationRead:
    if current_user.role == UserRole.COURIER and current_user.id != courier_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    location = service.get_current_for_courier(courier_user_id)
    ensure_location_access(current_user, location)
    return LocationRead.model_validate(location)
