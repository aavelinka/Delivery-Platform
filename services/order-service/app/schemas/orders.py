import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OrderStatus


class OrderCreate(BaseModel):
    user_id: uuid.UUID
    pickup_address: str = Field(min_length=3, max_length=1000)
    delivery_address: str = Field(min_length=3, max_length=1000)
    total_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    comment: str | None = Field(default=None, max_length=2000)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    courier_user_id: uuid.UUID | None = None
    changed_by: str | None = Field(default=None, max_length=128)


class OrderCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    changed_by: str | None = Field(default=None, max_length=128)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    courier_user_id: uuid.UUID | None = Field(validation_alias="courier_id")
    pickup_address: str
    delivery_address: str
    status: OrderStatus
    total_price: Decimal
    comment: str | None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None


class OrderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    event_type: str
    previous_status: OrderStatus | None
    new_status: OrderStatus | None
    changed_by: str | None
    payload: dict[str, Any]
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderRead]
    total: int
    limit: int
    offset: int


class OrderAdminSummary(BaseModel):
    total_orders: int
    orders_with_courier: int
    completed_orders: int
    cancelled_orders: int
    orders_by_status: dict[str, int]
