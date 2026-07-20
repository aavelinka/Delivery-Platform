import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    user_id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2, max_digits=12)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    payment_method: PaymentMethod = PaymentMethod.CARD
    description: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PaymentConfirm(BaseModel):
    changed_by: str | None = None
    provider_reference: str | None = Field(default=None, max_length=128)


class PaymentFail(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    changed_by: str | None = None


class PaymentRefund(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    changed_by: str | None = None


class PaymentRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    payment_method: PaymentMethod
    provider_reference: str | None
    description: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    failed_at: datetime | None
    refunded_at: datetime | None

    model_config = {"from_attributes": True}


class PaymentEventRead(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    event_type: str
    previous_status: PaymentStatus | None
    new_status: PaymentStatus | None
    changed_by: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: list[PaymentRead]
    total: int
    limit: int
    offset: int


class PaymentAdminSummary(BaseModel):
    total_payments: int
    pending_payments: int
    confirmed_payments: int
    failed_payments: int
    refunded_payments: int
    total_amount: Decimal
    confirmed_amount: Decimal
    refunded_amount: Decimal
    payments_by_status: dict[str, int]
