import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None


class UserProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str | None
    phone: str | None
    email: EmailStr | None
    created_at: datetime
    updated_at: datetime


class AddressCreate(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    city: str = Field(min_length=1, max_length=128)
    street: str = Field(min_length=1, max_length=255)
    building: str | None = Field(default=None, max_length=64)
    apartment: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, min_length=1, max_length=128)
    street: str | None = Field(default=None, min_length=1, max_length=255)
    building: str | None = Field(default=None, max_length=64)
    apartment: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)
    is_default: bool | None = None


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    label: str | None
    city: str
    street: str
    building: str | None
    apartment: str | None
    comment: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class UserAdminSummary(BaseModel):
    total_profiles: int
    total_addresses: int
    profiles_with_addresses: int
    default_addresses: int
