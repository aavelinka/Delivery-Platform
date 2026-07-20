import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    courier_user_id: uuid.UUID
    order_id: uuid.UUID | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    courier_user_id: uuid.UUID
    user_id: uuid.UUID | None
    order_id: uuid.UUID | None
    latitude: float
    longitude: float
    accuracy_meters: float | None
    recorded_at: datetime
    payload: dict[str, Any]


class TrackingAdminSummary(BaseModel):
    tracked_orders: int
    tracked_orders_with_courier: int
    location_updates_total: int
    location_updates_last_24h: int
