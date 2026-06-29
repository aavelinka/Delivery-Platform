import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, ensure_self_or_admin, get_current_user
from app.db.session import get_db
from app.schemas.users import (
    AddressCreate,
    AddressRead,
    AddressUpdate,
    UserProfileRead,
    UserProfileUpdate,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get("/{user_id}", response_model=UserProfileRead)
def get_profile(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserProfileRead:
    ensure_self_or_admin(current_user, user_id)
    return UserProfileRead.model_validate(service.get_or_create_profile(user_id))


@router.patch("/{user_id}", response_model=UserProfileRead)
def update_profile(
    user_id: uuid.UUID,
    payload: UserProfileUpdate,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserProfileRead:
    ensure_self_or_admin(current_user, user_id)
    return UserProfileRead.model_validate(service.update_profile(user_id, payload))


@router.get("/{user_id}/addresses", response_model=list[AddressRead])
def list_addresses(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[AddressRead]:
    ensure_self_or_admin(current_user, user_id)
    return [AddressRead.model_validate(item) for item in service.list_addresses(user_id)]


@router.post(
    "/{user_id}/addresses",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
)
def create_address(
    user_id: uuid.UUID,
    payload: AddressCreate,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> AddressRead:
    ensure_self_or_admin(current_user, user_id)
    return AddressRead.model_validate(service.create_address(user_id, payload))


@router.patch("/{user_id}/addresses/{address_id}", response_model=AddressRead)
def update_address(
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    payload: AddressUpdate,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> AddressRead:
    ensure_self_or_admin(current_user, user_id)
    return AddressRead.model_validate(service.update_address(user_id, address_id, payload))


@router.delete("/{user_id}/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    ensure_self_or_admin(current_user, user_id)
    service.delete_address(user_id, address_id)
