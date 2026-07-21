import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
from fastapi import HTTPException, status
from platform_common.auth import CurrentUser
from platform_common.tracing import get_traceparent

from app.core.config import Settings


@dataclass(frozen=True)
class DownstreamService:
    name: str
    base_url: str
    summary_path: str


@dataclass(frozen=True)
class PlatformSnapshot:
    generated_at: datetime
    service_health: list[dict[str, Any]]
    summaries: dict[str, dict[str, Any]]


class AdminService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_overview(self, current_user: CurrentUser, request_id: str) -> dict[str, Any]:
        snapshot = await self._collect_snapshot(current_user, request_id)
        return {
            "generated_at": snapshot.generated_at,
            "service_health": snapshot.service_health,
            "auth": snapshot.summaries["auth-service"],
            "users": snapshot.summaries["user-service"],
            "orders": snapshot.summaries["order-service"],
            "couriers": snapshot.summaries["courier-service"],
            "tracking": snapshot.summaries["tracking-service"],
            "notifications": snapshot.summaries["notification-service"],
            "payments": snapshot.summaries["payment-service"],
        }

    async def get_service_health(
        self,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict[str, Any]:
        del current_user, request_id
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            services = await asyncio.gather(
                *(self._fetch_health(client, service) for service in self._downstream_services())
            )
        return {"generated_at": datetime.now(UTC), "services": services}

    async def get_analytics(self, current_user: CurrentUser, request_id: str) -> dict[str, Any]:
        snapshot = await self._collect_snapshot(current_user, request_id)
        return {
            "generated_at": snapshot.generated_at,
            "service_health": snapshot.service_health,
            "health": self._build_health_rollup(snapshot.service_health),
            "activity": self._build_activity(snapshot.summaries),
            "financials": self._build_financials(snapshot.summaries),
            "conversion": self._build_conversion(snapshot.summaries),
            "alerts": self._build_alerts(snapshot.service_health, snapshot.summaries),
        }

    async def get_kafka_reliability(
        self,
        current_user: CurrentUser,
        request_id: str,
    ) -> dict[str, Any]:
        headers = self._internal_headers(current_user, request_id)
        services = self._kafka_reliability_services()

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            results = await asyncio.gather(
                *(self._fetch_summary(client, service, headers) for service in services)
            )

        return {
            "generated_at": datetime.now(UTC),
            "services": [
                {"service": name, **payload}
                for name, payload in results
            ],
        }

    def _downstream_services(self) -> tuple[DownstreamService, ...]:
        return (
            DownstreamService(
                "auth-service",
                self.settings.auth_service_url,
                "/auth/admin/summary",
            ),
            DownstreamService(
                "user-service",
                self.settings.user_service_url,
                "/users/admin/summary",
            ),
            DownstreamService(
                "order-service",
                self.settings.order_service_url,
                "/orders/admin/summary",
            ),
            DownstreamService(
                "courier-service",
                self.settings.courier_service_url,
                "/couriers/admin/summary",
            ),
            DownstreamService(
                "tracking-service",
                self.settings.tracking_service_url,
                "/tracking/admin/summary",
            ),
            DownstreamService(
                "notification-service",
                self.settings.notification_service_url,
                "/notifications/admin/summary",
            ),
            DownstreamService(
                "payment-service",
                self.settings.payment_service_url,
                "/payments/admin/summary",
            ),
        )

    def _kafka_reliability_services(self) -> tuple[DownstreamService, ...]:
        return (
            DownstreamService(
                "order-service",
                self.settings.order_service_url,
                "/orders/admin/kafka/reliability",
            ),
            DownstreamService(
                "courier-service",
                self.settings.courier_service_url,
                "/couriers/admin/kafka/reliability",
            ),
            DownstreamService(
                "tracking-service",
                self.settings.tracking_service_url,
                "/tracking/admin/kafka/reliability",
            ),
            DownstreamService(
                "notification-service",
                self.settings.notification_service_url,
                "/notifications/admin/kafka/reliability",
            ),
        )

    def _internal_headers(self, current_user: CurrentUser, request_id: str) -> dict[str, str]:
        if self.settings.gateway_internal_secret is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gateway internal secret is not configured",
            )

        headers = {
            "x-gateway-secret": self.settings.gateway_internal_secret,
            "x-user-id": str(current_user.id),
            "x-user-role": current_user.role.value,
            "x-request-id": request_id,
        }
        if current_user.email is not None:
            headers["x-user-email"] = current_user.email
        traceparent = get_traceparent()
        if traceparent is not None:
            headers["traceparent"] = traceparent
        return headers

    async def _fetch_summary(
        self,
        client: httpx.AsyncClient,
        service: DownstreamService,
        headers: dict[str, str],
    ) -> tuple[str, dict[str, Any]]:
        response = await self._request(client, service, service.summary_path, headers)
        payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{service.name} returned an invalid summary payload",
            )
        return service.name, {str(key): value for key, value in payload.items()}

    async def _fetch_health(
        self,
        client: httpx.AsyncClient,
        service: DownstreamService,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        url = self._service_url(service, "/health")
        try:
            response = await client.get(url)
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            is_json = response.headers.get("content-type", "").startswith("application/json")
            payload = response.json() if is_json else {}
            if response.is_success:
                service_status = payload.get("status") if isinstance(payload, dict) else None
                return {
                    "service": service.name,
                    "url": url,
                    "ok": True,
                    "status": str(service_status or "ok"),
                    "latency_ms": latency_ms,
                    "detail": None,
                }
            return {
                "service": service.name,
                "url": url,
                "ok": False,
                "status": f"http_{response.status_code}",
                "latency_ms": latency_ms,
                "detail": response.text[:200],
            }
        except httpx.HTTPError as exc:
            return {
                "service": service.name,
                "url": url,
                "ok": False,
                "status": "unavailable",
                "latency_ms": None,
                "detail": str(exc),
            }

    async def _request(
        self,
        client: httpx.AsyncClient,
        service: DownstreamService,
        path: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            response = await client.get(self._service_url(service, path), headers=headers)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{service.name} returned {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{service.name} is unavailable",
            ) from exc

    @staticmethod
    def _service_url(service: DownstreamService, path: str) -> str:
        return f"{service.base_url.rstrip('/')}{path}"

    async def _collect_snapshot(
        self,
        current_user: CurrentUser,
        request_id: str,
    ) -> PlatformSnapshot:
        headers = self._internal_headers(current_user, request_id)
        services = self._downstream_services()

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            health_results, summary_results = await asyncio.gather(
                asyncio.gather(*(self._fetch_health(client, service) for service in services)),
                asyncio.gather(
                    *(self._fetch_summary(client, service, headers) for service in services)
                ),
            )

        return PlatformSnapshot(
            generated_at=datetime.now(UTC),
            service_health=health_results,
            summaries={name: payload for name, payload in summary_results},
        )

    def _build_health_rollup(self, service_health: list[dict[str, Any]]) -> dict[str, Any]:
        total_services = len(service_health)
        healthy_services = sum(1 for item in service_health if item.get("ok") is True)
        latencies = [
            float(item["latency_ms"])
            for item in service_health
            if item.get("latency_ms") is not None
        ]
        slowest_service = None
        if latencies:
            slowest_service = max(
                (
                    item
                    for item in service_health
                    if item.get("latency_ms") is not None
                ),
                key=lambda item: float(item["latency_ms"]),
            )["service"]
        return {
            "total_services": total_services,
            "healthy_services": healthy_services,
            "degraded_services": total_services - healthy_services,
            "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "slowest_service": slowest_service,
        }

    def _build_activity(self, summaries: dict[str, dict[str, Any]]) -> dict[str, int]:
        auth = summaries["auth-service"]
        users = summaries["user-service"]
        orders = summaries["order-service"]
        couriers = summaries["courier-service"]
        tracking = summaries["tracking-service"]
        notifications = summaries["notification-service"]
        payments = summaries["payment-service"]

        total_orders = self._int_value(orders, "total_orders")
        orders_with_courier = self._int_value(orders, "orders_with_courier")

        return {
            "total_users": self._int_value(auth, "total_users"),
            "total_profiles": self._int_value(users, "total_profiles"),
            "total_orders": total_orders,
            "orders_without_courier": max(total_orders - orders_with_courier, 0),
            "active_couriers": self._int_value(couriers, "active_couriers"),
            "tracked_orders": self._int_value(tracking, "tracked_orders"),
            "total_payments": self._int_value(payments, "total_payments"),
            "total_notifications": self._int_value(
                notifications,
                "total_notifications",
            ),
            "unread_notifications": self._int_value(
                notifications,
                "unread_notifications",
            ),
            "location_updates_last_24h": self._int_value(
                tracking,
                "location_updates_last_24h",
            ),
        }

    def _build_financials(self, summaries: dict[str, dict[str, Any]]) -> dict[str, Decimal]:
        payments = summaries["payment-service"]
        total_payments = self._int_value(payments, "total_payments")
        confirmed_payments = self._int_value(payments, "confirmed_payments")
        total_amount = self._decimal_value(payments, "total_amount")
        confirmed_amount = self._decimal_value(payments, "confirmed_amount")
        refunded_amount = self._decimal_value(payments, "refunded_amount")

        return {
            "total_amount": total_amount,
            "confirmed_amount": confirmed_amount,
            "refunded_amount": refunded_amount,
            "average_payment_value": self._average_amount(total_amount, total_payments),
            "average_confirmed_payment_value": self._average_amount(
                confirmed_amount,
                confirmed_payments,
            ),
        }

    def _build_conversion(self, summaries: dict[str, dict[str, Any]]) -> dict[str, float]:
        users = summaries["user-service"]
        orders = summaries["order-service"]
        couriers = summaries["courier-service"]
        tracking = summaries["tracking-service"]
        notifications = summaries["notification-service"]
        payments = summaries["payment-service"]

        return {
            "profile_coverage_pct": self._percentage(
                self._int_value(users, "profiles_with_addresses"),
                self._int_value(users, "total_profiles"),
            ),
            "courier_assignment_pct": self._percentage(
                self._int_value(orders, "orders_with_courier"),
                self._int_value(orders, "total_orders"),
            ),
            "courier_activity_pct": self._percentage(
                self._int_value(couriers, "active_couriers"),
                self._int_value(couriers, "total_couriers"),
            ),
            "tracking_coverage_pct": self._percentage(
                self._int_value(tracking, "tracked_orders"),
                self._int_value(orders, "total_orders"),
            ),
            "order_completion_pct": self._percentage(
                self._int_value(orders, "completed_orders"),
                self._int_value(orders, "total_orders"),
            ),
            "order_cancellation_pct": self._percentage(
                self._int_value(orders, "cancelled_orders"),
                self._int_value(orders, "total_orders"),
            ),
            "payment_confirmation_pct": self._percentage(
                self._int_value(payments, "confirmed_payments"),
                self._int_value(payments, "total_payments"),
            ),
            "payment_failure_pct": self._percentage(
                self._int_value(payments, "failed_payments"),
                self._int_value(payments, "total_payments"),
            ),
            "refund_rate_pct": self._percentage(
                self._int_value(payments, "refunded_payments"),
                self._int_value(payments, "total_payments"),
            ),
            "notification_read_pct": self._percentage(
                self._int_value(notifications, "read_notifications"),
                self._int_value(notifications, "total_notifications"),
            ),
        }

    def _build_alerts(
        self,
        service_health: list[dict[str, Any]],
        summaries: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []

        degraded_services = [
            item["service"]
            for item in service_health
            if item.get("ok") is not True
        ]
        if degraded_services:
            alerts.append(
                {
                    "code": "services_degraded",
                    "severity": "warning",
                    "message": (
                        "Unavailable or degraded services: "
                        + ", ".join(sorted(degraded_services))
                    ),
                }
            )

        orders = summaries["order-service"]
        tracking = summaries["tracking-service"]
        notifications = summaries["notification-service"]
        payments = summaries["payment-service"]

        total_orders = self._int_value(orders, "total_orders")
        orders_with_courier = self._int_value(orders, "orders_with_courier")
        orders_without_courier = max(total_orders - orders_with_courier, 0)
        if orders_without_courier > 0:
            alerts.append(
                {
                    "code": "orders_waiting_courier",
                    "severity": "warning",
                    "message": f"{orders_without_courier} orders do not have a courier yet",
                }
            )

        tracked_orders_with_courier = self._int_value(tracking, "tracked_orders_with_courier")
        tracking_gap = max(orders_with_courier - tracked_orders_with_courier, 0)
        if tracking_gap > 0:
            alerts.append(
                {
                    "code": "tracking_gap",
                    "severity": "warning",
                    "message": f"{tracking_gap} courier-linked orders are missing tracking data",
                }
            )

        payment_failure_pct = self._percentage(
            self._int_value(payments, "failed_payments"),
            self._int_value(payments, "total_payments"),
        )
        if payment_failure_pct >= 15.0:
            alerts.append(
                {
                    "code": "payment_failures_high",
                    "severity": "warning",
                    "message": f"Payment failure rate is {payment_failure_pct:.2f}%",
                }
            )

        total_notifications = self._int_value(notifications, "total_notifications")
        read_notifications = self._int_value(notifications, "read_notifications")
        unread_notifications = self._int_value(notifications, "unread_notifications")
        if total_notifications >= 10 and unread_notifications > read_notifications:
            alerts.append(
                {
                    "code": "notifications_unread_backlog",
                    "severity": "info",
                    "message": (
                        f"{unread_notifications} notifications remain unread "
                        f"out of {total_notifications}"
                    ),
                }
            )

        return alerts

    @staticmethod
    def _int_value(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _decimal_value(payload: dict[str, Any], key: str) -> Decimal:
        value = payload.get(key, "0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100, 2)

    @staticmethod
    def _average_amount(total: Decimal, count: int) -> Decimal:
        if count <= 0:
            return Decimal("0.00")
        return (total / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
