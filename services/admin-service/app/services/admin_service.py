import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
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


class AdminService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_overview(self, current_user: CurrentUser, request_id: str) -> dict[str, Any]:
        headers = self._internal_headers(current_user, request_id)
        services = self._downstream_services()

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            health_results, summary_results = await asyncio.gather(
                asyncio.gather(*(self._fetch_health(client, service) for service in services)),
                asyncio.gather(
                    *(self._fetch_summary(client, service, headers) for service in services)
                ),
            )

        summaries = {name: payload for name, payload in summary_results}
        return {
            "generated_at": datetime.now(UTC),
            "service_health": health_results,
            "auth": summaries["auth-service"],
            "users": summaries["user-service"],
            "orders": summaries["order-service"],
            "couriers": summaries["courier-service"],
            "tracking": summaries["tracking-service"],
            "notifications": summaries["notification-service"],
            "payments": summaries["payment-service"],
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
