from datetime import datetime
from decimal import Decimal
from typing import Literal

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


class AdminHealthRollupRead(BaseModel):
    total_services: int
    healthy_services: int
    degraded_services: int
    average_latency_ms: float | None = None
    slowest_service: str | None = None


class AdminActivityRead(BaseModel):
    total_users: int
    total_profiles: int
    total_orders: int
    orders_without_courier: int
    active_couriers: int
    tracked_orders: int
    total_payments: int
    total_notifications: int
    unread_notifications: int
    location_updates_last_24h: int


class AdminFinancialsRead(BaseModel):
    total_amount: Decimal
    confirmed_amount: Decimal
    refunded_amount: Decimal
    average_payment_value: Decimal
    average_confirmed_payment_value: Decimal


class AdminConversionRead(BaseModel):
    profile_coverage_pct: float
    courier_assignment_pct: float
    courier_activity_pct: float
    tracking_coverage_pct: float
    order_completion_pct: float
    order_cancellation_pct: float
    payment_confirmation_pct: float
    payment_failure_pct: float
    refund_rate_pct: float
    notification_read_pct: float


class AdminAlertRead(BaseModel):
    code: str
    severity: Literal["info", "warning"]
    message: str


class AdminAnalyticsRead(BaseModel):
    generated_at: datetime
    service_health: list[ServiceHealthEntryRead]
    health: AdminHealthRollupRead
    activity: AdminActivityRead
    financials: AdminFinancialsRead
    conversion: AdminConversionRead
    alerts: list[AdminAlertRead]


class KafkaReliabilityEntryRead(BaseModel):
    service: str
    consumer_enabled: bool
    consumer_group: str
    source_topics: list[str]
    dlq_topic: str
    max_retries: int
    retry_backoff_seconds: float


class AdminKafkaReliabilityRead(BaseModel):
    generated_at: datetime
    services: list[KafkaReliabilityEntryRead]
