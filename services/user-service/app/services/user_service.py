import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserAddress, UserProfile
from app.schemas.users import AddressCreate, AddressUpdate, UserProfileUpdate


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_profile(self, user_id: uuid.UUID) -> UserProfile:
        profile = self.db.get(UserProfile, user_id)
        if profile is not None:
            return profile

        profile = UserProfile(user_id=user_id)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_profile(self, user_id: uuid.UUID, data: UserProfileUpdate) -> UserProfile:
        profile = self.get_or_create_profile(user_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def list_addresses(self, user_id: uuid.UUID) -> list[UserAddress]:
        self.get_or_create_profile(user_id)
        return list(
            self.db.scalars(
                select(UserAddress)
                .where(UserAddress.user_id == user_id)
                .order_by(UserAddress.created_at.asc())
            ).all()
        )

    def create_address(self, user_id: uuid.UUID, data: AddressCreate) -> UserAddress:
        self.get_or_create_profile(user_id)
        if data.is_default:
            self._clear_default_address(user_id)
        address = UserAddress(user_id=user_id, **data.model_dump())
        self.db.add(address)
        self.db.commit()
        self.db.refresh(address)
        return address

    def update_address(
        self,
        user_id: uuid.UUID,
        address_id: uuid.UUID,
        data: AddressUpdate,
    ) -> UserAddress:
        address = self._get_user_address(user_id, address_id)
        updates = data.model_dump(exclude_unset=True)
        if updates.get("is_default") is True:
            self._clear_default_address(user_id)
        for field, value in updates.items():
            setattr(address, field, value)
        address.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(address)
        return address

    def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> None:
        address = self._get_user_address(user_id, address_id)
        self.db.delete(address)
        self.db.commit()

    def _get_user_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> UserAddress:
        address = self.db.scalar(
            select(UserAddress)
            .where(UserAddress.id == address_id)
            .where(UserAddress.user_id == user_id)
        )
        if address is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
        return address

    def _clear_default_address(self, user_id: uuid.UUID) -> None:
        for address in self.list_addresses(user_id):
            address.is_default = False
