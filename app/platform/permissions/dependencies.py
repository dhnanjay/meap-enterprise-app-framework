"""Authorization — server-side permission enforcement (Section 41).

Permission names follow: module.resource.action

Navigation hiding is a convenience, not a security control.
A user lacking a permission must remain unable to invoke the operation
even via direct HTTP request.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.platform.auth.context import UserContext, get_current_user
from app.platform.errors.taxonomy import AuthorizationError
from app.settings import get_settings


def require_workspace_admin(
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Require the effective workspace-administrator role."""
    if "workspace_admin" not in user.roles and user.role not in {
        "admin",
        "workspace_admin",
    }:
        raise AuthorizationError(
            module="platform",
            operation="workspace_administration",
            reason_code="PERMISSION_DENIED",
            safe_message="Workspace administrator access is required",
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    return user


def require_permission(permission: str):
    """FastAPI dependency factory: enforce a permission server-side.

    Usage:
        @router.post("/run", dependencies=[Depends(require_permission("bank_reconciliation.execute"))])
        def run_reconciliation(...): ...
    """

    def _check(request: Request, user: UserContext = Depends(get_current_user)) -> UserContext:
        settings = getattr(request.app.state, "settings", get_settings())

        # When auth is disabled (local dev), allow all registered permissions
        if not settings.auth_enabled:
            return user

        # In production, check the user's permission set
        if permission not in user.permissions:
            raise AuthorizationError(
                module=permission.split(".")[0] if "." in permission else "platform",
                operation="require_permission",
                reason_code="PERMISSION_DENIED",
                safe_message=f"You do not have permission: {permission}",
                correlation_id=getattr(request.state, "correlation_id", None),
            )

        return user

    return _check
