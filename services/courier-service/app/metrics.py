from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.courier_service import CourierService

_COURIER_METRICS = (
    SummaryMetricDefinition(
        name="delivery_couriers_total",
        description="Total number of couriers.",
        summary_key="total_couriers",
    ),
    SummaryMetricDefinition(
        name="delivery_couriers_active_total",
        description="Total number of active couriers.",
        summary_key="active_couriers",
    ),
    SummaryMetricDefinition(
        name="delivery_couriers_inactive_total",
        description="Total number of inactive couriers.",
        summary_key="inactive_couriers",
    ),
    SummaryMetricDefinition(
        name="delivery_couriers_by_availability",
        description="Couriers grouped by availability.",
        summary_key="couriers_by_availability",
        label_name="availability",
    ),
    SummaryMetricDefinition(
        name="delivery_courier_assignments_by_status",
        description="Courier assignments grouped by status.",
        summary_key="assignments_by_status",
        label_name="status",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_courier_summary, metrics=_COURIER_METRICS)


def _load_courier_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return CourierService(db).get_admin_summary()
