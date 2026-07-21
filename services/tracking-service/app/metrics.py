from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.tracking_service import TrackingService

_TRACKING_METRICS = (
    SummaryMetricDefinition(
        name="delivery_tracking_orders_total",
        description="Total number of tracked orders.",
        summary_key="tracked_orders",
    ),
    SummaryMetricDefinition(
        name="delivery_tracking_orders_with_courier_total",
        description="Total number of tracked orders with a courier assigned.",
        summary_key="tracked_orders_with_courier",
    ),
    SummaryMetricDefinition(
        name="delivery_tracking_location_updates_total",
        description="Total number of stored courier location updates.",
        summary_key="location_updates_total",
    ),
    SummaryMetricDefinition(
        name="delivery_tracking_location_updates_last_24h_total",
        description="Courier location updates received during the last 24 hours.",
        summary_key="location_updates_last_24h",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_tracking_summary, metrics=_TRACKING_METRICS)


def _load_tracking_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return TrackingService(db).get_admin_summary()
