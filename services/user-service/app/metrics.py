from collections.abc import Mapping

from fastapi import FastAPI
from platform_common.observability import SummaryMetricDefinition, register_summary_metrics

from app.db.session import SessionLocal
from app.services.user_service import UserService

_USER_METRICS = (
    SummaryMetricDefinition(
        name="delivery_user_profiles_total",
        description="Total number of user profiles.",
        summary_key="total_profiles",
    ),
    SummaryMetricDefinition(
        name="delivery_user_addresses_total",
        description="Total number of saved user addresses.",
        summary_key="total_addresses",
    ),
    SummaryMetricDefinition(
        name="delivery_user_profiles_with_addresses_total",
        description="Total number of user profiles with at least one address.",
        summary_key="profiles_with_addresses",
    ),
    SummaryMetricDefinition(
        name="delivery_user_default_addresses_total",
        description="Total number of default user addresses.",
        summary_key="default_addresses",
    ),
)


def register_domain_metrics(app: FastAPI) -> None:
    register_summary_metrics(app, load_summary=_load_user_summary, metrics=_USER_METRICS)


def _load_user_summary() -> Mapping[str, object]:
    with SessionLocal() as db:
        return UserService(db).get_admin_summary()
