from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AuthSummaryRead(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    users_by_role: dict[str, int]


class UserSummaryRead(BaseModel):
    total_profiles: int
    total_addresses: int
    profiles_with_addresses: int
    default_addresses: int


class OrderSummaryRead(BaseModel):
    total_orders: int
    orders_with_courier: int
    completed_orders: int
    cancelled_orders: int
    orders_by_status: dict[str, int]


class CourierSummaryRead(BaseModel):
    total_couriers: int
    active_couriers: int
    inactive_couriers: int
    couriers_by_availability: dict[str, int]
    assignments_by_status: dict[str, int]


class TrackingSummaryRead(BaseModel):
    tracked_orders: int
    tracked_orders_with_courier: int
    location_updates_total: int
    location_updates_last_24h: int


class NotificationSummaryRead(BaseModel):
    total_notifications: int
    read_notifications: int
    unread_notifications: int
    notifications_by_status: dict[str, int]
    notifications_by_channel: dict[str, int]


class PaymentSummaryRead(BaseModel):
    total_payments: int
    pending_payments: int
    confirmed_payments: int
    failed_payments: int
    refunded_payments: int
    total_amount: Decimal
    confirmed_amount: Decimal
    refunded_amount: Decimal
    payments_by_status: dict[str, int]


class ServiceHealthEntryRead(BaseModel):
    service: str
    url: str
    ok: bool
    status: str
    latency_ms: float | None = None
    detail: str | None = None


class AdminServiceHealthRead(BaseModel):
    generated_at: datetime
    services: list[ServiceHealthEntryRead]


class AdminOverviewRead(BaseModel):
    generated_at: datetime
    service_health: list[ServiceHealthEntryRead]
    auth: AuthSummaryRead
    users: UserSummaryRead
    orders: OrderSummaryRead
    couriers: CourierSummaryRead
    tracking: TrackingSummaryRead
    notifications: NotificationSummaryRead
    payments: PaymentSummaryRead
