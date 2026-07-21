from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.notification_service import NotificationService

_NOTIFICATION_METRICS = (
    SummaryMetricDefinition(
        name="delivery_notifications_total",
        description="Total number of notifications.",
        summary_key="total_notifications",
    ),
    SummaryMetricDefinition(
        name="delivery_notifications_read_total",
        description="Total number of read notifications.",
        summary_key="read_notifications",
    ),
    SummaryMetricDefinition(
        name="delivery_notifications_unread_total",
        description="Total number of unread notifications.",
        summary_key="unread_notifications",
    ),
    SummaryMetricDefinition(
        name="delivery_notifications_by_status",
        description="Notifications grouped by status.",
        summary_key="notifications_by_status",
        label_name="status",
    ),
    SummaryMetricDefinition(
        name="delivery_notifications_by_channel",
        description="Notifications grouped by channel.",
        summary_key="notifications_by_channel",
        label_name="channel",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(
        app,
        load_summary=_load_notification_summary,
        metrics=_NOTIFICATION_METRICS,
    )


def _load_notification_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return NotificationService(db).get_admin_summary()
