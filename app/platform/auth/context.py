"""Authentication context (Section 40).

Authentication is Platform infrastructure, not a business module.
In local development it is disabled — the default user is returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from app.settings import get_settings


@dataclass(frozen=True)
class UserContext:
    """The authenticated user's identity and permissions."""

    user_id: str
    username: str
    display_name: str
    email: str | None = None
    permissions: frozenset[str] = frozenset()
    is_authenticated: bool = True


# Default dev user when auth is disabled
_DEV_USER = UserContext(
    user_id="dev-user",
    username="developer",
    display_name="Developer (Local)",
    permissions=frozenset(),  # permissions granted at check time when auth disabled
)


def get_current_user(request: Request) -> UserContext:
    """FastAPI dependency: return the current user context.

    When auth is disabled (local dev), returns a dev user with all permissions.
    When enabled, this is where you'd integrate Entra ID / OIDC / etc.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        return _DEV_USER

    # In production, integrate your identity provider here.
    # Example: extract from request.session after OIDC middleware.
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    return _DEV_USER