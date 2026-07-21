from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.payment_service import PaymentService

_PAYMENT_METRICS = (
    SummaryMetricDefinition(
        name="delivery_payments_total",
        description="Total number of payments.",
        summary_key="total_payments",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_pending_total",
        description="Total number of pending payments.",
        summary_key="pending_payments",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_confirmed_total",
        description="Total number of confirmed payments.",
        summary_key="confirmed_payments",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_failed_total",
        description="Total number of failed payments.",
        summary_key="failed_payments",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_refunded_total",
        description="Total number of refunded payments.",
        summary_key="refunded_payments",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_amount_total",
        description="Total amount across all payments.",
        summary_key="total_amount",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_confirmed_amount_total",
        description="Total amount across confirmed payments.",
        summary_key="confirmed_amount",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_refunded_amount_total",
        description="Total amount across refunded payments.",
        summary_key="refunded_amount",
    ),
    SummaryMetricDefinition(
        name="delivery_payments_by_status",
        description="Payments grouped by status.",
        summary_key="payments_by_status",
        label_name="status",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_payment_summary, metrics=_PAYMENT_METRICS)


def _load_payment_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return PaymentService(db).get_admin_summary()
