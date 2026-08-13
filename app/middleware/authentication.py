"""Resolve server-side sessions and enforce authentication and CSRF globally."""

from __future__ import annotations

import hmac
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.platform.auth.context import UserContext
from app.platform.auth.service import AuthService
from app.platform.database.session import get_session_factory


PUBLIC_PREFIXES = ("/auth/enroll/", "/static/")
PUBLIC_EXACT = {"/auth", "/auth/login", "/developer/health"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def session_cookie_name(profile: str) -> str:
    return "__Host-meap_session" if profile == "production" else "meap_session"


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = request.app.state.settings
        if not settings.auth_enabled:
            return await call_next(request)

        path = request.url.path
        is_public = path in PUBLIC_EXACT or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
        raw_token = request.cookies.get(session_cookie_name(settings.profile))
        auth_session = None
        if raw_token:
            factory = get_session_factory()
            with factory() as db:
                auth_session = AuthService(db, settings).resolve_session(raw_token)
                if auth_session:
                    permissions = frozenset(request.app.state.registry.all_permissions)
                    request.state.user = UserContext(
                        user_id=auth_session.user.user_id,
                        username=auth_session.user.normalized_email,
                        display_name=auth_session.user.display_name,
                        email=auth_session.user.email,
                        organization_id=auth_session.membership.organization_id,
                        membership_id=auth_session.membership_id,
                        role=auth_session.membership.role,
                        session_id=auth_session.session_id,
                        csrf_token=auth_session.csrf_token,
                        permissions=permissions,
                    )

        if auth_session is None and not is_public:
            next_path = path
            if request.url.query:
                next_path += "?" + request.url.query
            location = f"/auth/login?next={quote(next_path, safe='/')}"
            if request.headers.get("HX-Request") == "true":
                return Response(status_code=401, headers={"HX-Redirect": location})
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            return RedirectResponse(location, status_code=303)

        route_validates_form_csrf = path.startswith("/auth/")
        if auth_session and request.method in UNSAFE_METHODS and not is_public and not route_validates_form_csrf:
            submitted = request.headers.get("X-CSRF-Token", "")
            if not submitted or not hmac.compare_digest(submitted, auth_session.csrf_token):
                return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)

        return await call_next(request)
