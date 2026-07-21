import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import AssignmentStatus, CourierAvailability


class CourierCreate(BaseModel):
    user_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    vehicle_type: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class CourierUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    vehicle_type: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class CourierAvailabilityUpdate(BaseModel):
    availability: CourierAvailability
    changed_by: str | None = Field(default=None, max_length=128)


class AssignmentCreate(BaseModel):
    courier_id: uuid.UUID
    order_id: uuid.UUID
    changed_by: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class AssignmentStatusUpdate(BaseModel):
    status: AssignmentStatus
    changed_by: str | None = Field(default=None, max_length=128)


class CourierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    phone: str | None
    vehicle_type: str | None
    city: str | None
    availability: CourierAvailability
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    courier_id: uuid.UUID
    order_id: uuid.UUID
    status: AssignmentStatus
    assigned_at: datetime
    accepted_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    payload: dict[str, Any]


class CourierListResponse(BaseModel):
    items: list[CourierRead]
    total: int
    limit: int
    offset: int


class AssignmentListResponse(BaseModel):
    items: list[AssignmentRead]
    total: int
    limit: int
    offset: int


class CourierAdminSummary(BaseModel):
    total_couriers: int
    active_couriers: int
    inactive_couriers: int
    couriers_by_availability: dict[str, int]
    assignments_by_status: dict[str, int]


class CourierKafkaReliabilityRead(BaseModel):
    consumer_enabled: bool
    consumer_group: str
    source_topics: list[str]
    dlq_topic: str
    max_retries: int
    retry_backoff_seconds: float
