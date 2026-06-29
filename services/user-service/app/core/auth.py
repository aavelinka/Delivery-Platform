from platform_common.auth import (
    CurrentUser,
    UserRole,
    build_get_current_user,
    ensure_self_or_admin,
)

from app.core.config import get_settings

get_current_user = build_get_current_user(get_settings)
