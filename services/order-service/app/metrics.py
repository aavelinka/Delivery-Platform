from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.order_service import OrderService

_ORDER_METRICS = (
    SummaryMetricDefinition(
        name="delivery_orders_total",
        description="Total number of orders.",
        summary_key="total_orders",
    ),
    SummaryMetricDefinition(
        name="delivery_orders_with_courier_total",
        description="Total number of orders assigned to a courier.",
        summary_key="orders_with_courier",
    ),
    SummaryMetricDefinition(
        name="delivery_orders_completed_total",
        description="Total number of delivered orders.",
        summary_key="completed_orders",
    ),
    SummaryMetricDefinition(
        name="delivery_orders_cancelled_total",
        description="Total number of cancelled orders.",
        summary_key="cancelled_orders",
    ),
    SummaryMetricDefinition(
        name="delivery_orders_by_status",
        description="Orders grouped by status.",
        summary_key="orders_by_status",
        label_name="status",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_order_summary, metrics=_ORDER_METRICS)


def _load_order_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return OrderService(db).get_admin_summary()
