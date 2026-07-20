from fastapi import APIRouter, Depends, Request
from platform_common.observability import get_request_id

from app.core.auth import CurrentUser, UserRole, require_roles
from app.core.config import Settings, get_settings
from app.schemas.admin import AdminOverviewRead, AdminServiceHealthRead
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_service(settings: Settings = Depends(get_settings)) -> AdminService:
    return AdminService(settings)


@router.get("/overview", response_model=AdminOverviewRead)
async def get_overview(
    request: Request,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    service: AdminService = Depends(get_admin_service),
) -> AdminOverviewRead:
    overview = await service.get_overview(current_user, get_request_id(request))
    return AdminOverviewRead.model_validate(overview)


@router.get("/services/health", response_model=AdminServiceHealthRead)
async def get_services_health(
    request: Request,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    service: AdminService = Depends(get_admin_service),
) -> AdminServiceHealthRead:
    health = await service.get_service_health(current_user, get_request_id(request))
    return AdminServiceHealthRead.model_validate(health)
