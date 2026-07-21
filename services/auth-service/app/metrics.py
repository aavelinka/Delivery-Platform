from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.auth_service import AuthService

_AUTH_METRICS = (
    SummaryMetricDefinition(
        name="delivery_auth_users_total",
        description="Total number of users in the auth service.",
        summary_key="total_users",
    ),
    SummaryMetricDefinition(
        name="delivery_auth_users_active_total",
        description="Total number of active auth users.",
        summary_key="active_users",
    ),
    SummaryMetricDefinition(
        name="delivery_auth_users_inactive_total",
        description="Total number of inactive auth users.",
        summary_key="inactive_users",
    ),
    SummaryMetricDefinition(
        name="delivery_auth_users_by_role",
        description="Auth users grouped by role.",
        summary_key="users_by_role",
        label_name="role",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_auth_summary, metrics=_AUTH_METRICS)


def _load_auth_summary() -> Mapping[str, object]:
    settings = get_settings()
    with SessionLocal() as db:
        return AuthService(db, settings).get_admin_summary()
