from platform_common.auth import (
    CurrentUser,
    build_get_current_user,
    ensure_self_or_admin,
)

from app.core.config import get_settings

__all__ = ["CurrentUser", "ensure_self_or_admin", "get_current_user"]

get_current_user = build_get_current_user(get_settings)
