"""HTML routes for local TOTP enrollment, login, logout, and administration."""

from __future__ import annotations

import hmac
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.middleware.authentication import session_cookie_name
from app.platform.audit.service import AuditService
from app.platform.auth.context import UserContext, get_current_user
from app.platform.auth.models import AuthSession, Credential, Membership, RecoveryCode
from app.platform.auth.service import AuthService, now_utc
from app.platform.database.session import get_db
from app.platform.permissions.roles import DEFAULT_ROLE_BUNDLES
from app.platform.templates.rendering import templates

router = APIRouter(prefix="/auth", tags=["authentication"])


def _access_admin_context(
    request: Request,
    db: Session,
    user: UserContext,
    *,
    invite_url: str | None = None,
    error: str | None = None,
    message: str | None = None,
) -> dict:
    memberships = db.scalars(
        select(Membership)
        .where(Membership.organization_id == user.organization_id)
        .order_by(Membership.created_at)
    ).all()
    registry = request.app.state.registry
    navigation_items = registry.get_configurable_navigation()
    service = AuthService(db, request.app.state.settings)
    access = {
        membership.membership_id: service.permissions_for_membership(
            membership.membership_id,
            frozenset(registry.all_permissions),
        )[0]
        for membership in memberships
    }
    return {
        "current_user": user,
        "memberships": memberships,
        "navigation_items": navigation_items,
        "membership_permissions": access,
        "invite_url": invite_url,
        "error": error,
        "message": message,
        "role_definitions": DEFAULT_ROLE_BUNDLES,
    }


def _is_workspace_admin(user: UserContext) -> bool:
    return "workspace_admin" in user.roles or user.role in {"admin", "workspace_admin"}


def _admin_membership(db: Session, user: UserContext, membership_id: str) -> Membership | None:
    if not _is_workspace_admin(user):
        return None
    membership = db.get(Membership, membership_id)
    if membership is None or membership.organization_id != user.organization_id:
        return None
    return membership


def _account_context(
    request: Request,
    db: Session,
    user: UserContext,
    membership: Membership,
    *,
    error: str | None = None,
) -> dict:
    moment = now_utc()
    last_login_at = db.scalar(
        select(func.max(AuthSession.created_at)).where(
            AuthSession.membership_id == membership.membership_id
        )
    )
    last_seen_at = db.scalar(
        select(func.max(AuthSession.last_seen_at)).where(
            AuthSession.membership_id == membership.membership_id
        )
    )
    active_sessions = db.scalar(
        select(func.count(AuthSession.session_id)).where(
            AuthSession.membership_id == membership.membership_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.idle_expires_at > moment,
            AuthSession.absolute_expires_at > moment,
        )
    ) or 0
    credential = db.scalar(
        select(Credential)
        .where(Credential.user_id == membership.user_id)
        .order_by(Credential.enrolled_at.desc())
    )
    recovery_codes_remaining = db.scalar(
        select(func.count(RecoveryCode.recovery_code_id)).where(
            RecoveryCode.user_id == membership.user_id,
            RecoveryCode.consumed_at.is_(None),
        )
    ) or 0
    return {
        "current_user": user,
        "membership": membership,
        "roles": DEFAULT_ROLE_BUNDLES,
        "last_login_at": last_login_at,
        "last_seen_at": last_seen_at,
        "active_sessions": active_sessions,
        "credential": credential,
        "recovery_codes_remaining": recovery_codes_remaining,
        "error": error,
    }


_ADMIN_ACTIONS = {
    "change-role": {
        "title": "Confirm role change",
        "warning": "The user's active sessions will be revoked so the new role takes effect immediately.",
        "button": "Change role",
    },
    "suspend": {
        "title": "Confirm account suspension",
        "warning": "The user will lose access immediately and every active session will be revoked.",
        "button": "Suspend account",
    },
    "reactivate": {
        "title": "Confirm account reactivation",
        "warning": "The user will be able to sign in again using the existing enrolled authenticator.",
        "button": "Reactivate account",
    },
    "revoke-sessions": {
        "title": "Confirm session revocation",
        "warning": "Every active session for this user will be terminated immediately.",
        "button": "Revoke all sessions",
    },
    "reenroll": {
        "title": "Confirm authenticator reset",
        "warning": "The current authenticator, recovery codes, and sessions will stop working. A new one-time enrollment link will be issued.",
        "button": "Reset authenticator",
    },
    "recovery-codes": {
        "title": "Confirm recovery-code replacement",
        "warning": "Every existing recovery code will stop working. The replacements are displayed only once.",
        "button": "Replace recovery codes",
    },
    "navigation-access": {
        "title": "Confirm application-access change",
        "warning": "This changes both navigation visibility and direct route access for the selected application.",
        "button": "Change application access",
    },
}


def _auth_page(request: Request, template_name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    context = {"request": request, "settings": request.app.state.settings, **context}
    response = templates.TemplateResponse(request, template_name, context, status_code=status_code)
    response.headers.update({
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        ),
    })
    return response


def _form_csrf(request: Request, *, purpose: str) -> str:
    serializer = URLSafeTimedSerializer(
        request.app.state.settings.csrf_key,
        salt="meap-preauth-form-csrf-v1",
    )
    return serializer.dumps({"purpose": purpose})


def _valid_form_csrf(request: Request, submitted: str, *, purpose: str) -> bool:
    serializer = URLSafeTimedSerializer(
        request.app.state.settings.csrf_key,
        salt="meap-preauth-form-csrf-v1",
    )
    try:
        payload = serializer.loads(submitted, max_age=900)
    except (BadSignature, SignatureExpired):
        return False
    return hmac.compare_digest(str(payload.get("purpose", "")), purpose)


def _safe_next(value: str) -> str:
    parsed = urlparse(value)
    return value if value.startswith("/") and not parsed.netloc and not value.startswith("//") else "/"


def _valid_session_csrf(user: UserContext, submitted: str) -> bool:
    return bool(user.csrf_token and submitted and hmac.compare_digest(user.csrf_token, submitted))


@router.get("/login", response_class=HTMLResponse, name="auth.login")
def login_page(request: Request, next: str = "/"):
    if getattr(request.state, "user", None):
        return RedirectResponse(_safe_next(next), status_code=303)
    csrf = _form_csrf(request, purpose="login")
    response = _auth_page(
        request,
        "auth/login.html",
        {"csrf_token": csrf, "next_path": _safe_next(next), "error": None},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    next: str = Form("/"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    if not _valid_form_csrf(request, csrf_token, purpose="login"):
        return _auth_page(request, "auth/login.html", {
            "csrf_token": csrf_token,
            "next_path": _safe_next(next),
            "error": "The sign-in form expired. Refresh and try again.",
        }, 403)
    service = AuthService(db, request.app.state.settings)
    result = service.authenticate(
        email=email,
        code=code,
        ip=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", ""),
    )
    if result is None:
        response = _auth_page(request, "auth/login.html", {
            "csrf_token": csrf_token,
            "next_path": _safe_next(next),
            "error": "The email address or authentication code was not accepted.",
        }, 401)
        response.headers["Cache-Control"] = "no-store"
        return response
    response = RedirectResponse(_safe_next(next), status_code=303)
    settings = request.app.state.settings
    response.set_cookie(
        session_cookie_name(settings.profile),
        result.session_token,
        httponly=True,
        secure=settings.profile == "production",
        samesite="lax",
        path="/",
        max_age=settings.session_absolute_lifetime_hours * 3600,
    )
    return response


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _valid_session_csrf(user, csrf_token):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if user.session_id:
        AuthService(db, request.app.state.settings).revoke_session(user.session_id, user.user_id)
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(session_cookie_name(request.app.state.settings.profile), path="/")
    return response


@router.get("/enroll/{token}", response_class=HTMLResponse)
def enrollment_page(request: Request, token: str, db: Session = Depends(get_db)):
    service = AuthService(db, request.app.state.settings)
    enrollment = service.get_enrollment(token)
    if enrollment is None:
        return _auth_page(request, "auth/enrollment_invalid.html", {}, 410)
    csrf = _form_csrf(request, purpose=f"enrollment:{enrollment.enrollment_id}")
    response = _auth_page(request, "auth/enroll.html", {
        "token": token,
        "csrf_token": csrf,
        "qr_data_uri": service.enrollment_qr_data_uri(enrollment),
        "membership": enrollment.membership,
        "error": None,
    })
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return response


@router.post("/enroll/{token}", response_class=HTMLResponse)
def confirm_enrollment(
    request: Request,
    token: str,
    code: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    service = AuthService(db, request.app.state.settings)
    enrollment = service.get_enrollment(token)
    if enrollment is None:
        return _auth_page(request, "auth/enrollment_invalid.html", {}, 410)
    if not _valid_form_csrf(
        request,
        csrf_token,
        purpose=f"enrollment:{enrollment.enrollment_id}",
    ):
        error = "The enrollment form expired. Refresh and try again."
    else:
        try:
            membership, recovery_codes = service.confirm_enrollment(token, code)
            response = _auth_page(request, "auth/recovery_codes.html", {
                "membership": membership,
                "recovery_codes": recovery_codes,
            })
            response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            return response
        except ValueError as exc:
            error = str(exc)
    response = _auth_page(request, "auth/enroll.html", {
        "token": token,
        "csrf_token": csrf_token,
        "qr_data_uri": service.enrollment_qr_data_uri(enrollment),
        "membership": enrollment.membership,
        "error": error,
    }, 400)
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return response


@router.get("/admin/users", response_class=HTMLResponse)
def user_admin(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_workspace_admin(user):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    return _auth_page(
        request,
        "auth/users.html",
        _access_admin_context(request, db, user, message=message, error=error),
    )


@router.get("/admin/users/{membership_id}", response_class=HTMLResponse)
def user_admin_detail(
    request: Request,
    membership_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _admin_membership(db, user, membership_id)
    if membership is None:
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    return _auth_page(
        request,
        "auth/user_detail.html",
        _account_context(request, db, user, membership),
    )


@router.post("/admin/users/invite", response_class=HTMLResponse)
def invite_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    role: str = Form("member"),
    admin_code: str = Form(...),
    confirmation: str = Form(...),
    csrf_token: str = Form(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_workspace_admin(user):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if not _valid_session_csrf(user, csrf_token):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    service = AuthService(db, request.app.state.settings)
    error = None
    invite_url = None
    try:
        if confirmation != "confirmed":
            raise ValueError("Confirm that you intend to create this account")
        if not service.reauthenticate_administrator(
            user_id=user.user_id,
            code=admin_code,
            ip=request.client.host if request.client else "unknown",
        ):
            raise ValueError("Administrator reauthentication was not accepted")
        result = service.invite_user(
            organization_id=user.organization_id or "",
            email=email,
            display_name=display_name,
            role=role,
            actor_user_id=user.user_id,
        )
        invite_url = str(request.base_url).rstrip("/") + f"/auth/enroll/{result.token}"
    except ValueError as exc:
        error = str(exc)
        AuditService(db).record(
            event_type="auth.membership.invitation_failed",
            outcome="FAILED",
            organization_id=user.organization_id,
            actor_user_id=user.user_id,
            entity_type="organization",
            entity_id=user.organization_id,
            event_data={"reason": error},
        )
    return _auth_page(
        request,
        "auth/users.html",
        _access_admin_context(
            request, db, user, invite_url=invite_url, error=error
        ),
        400 if error else 200,
    )


@router.get("/admin/users/{membership_id}/confirm/{action}", response_class=HTMLResponse)
def confirm_admin_action(
    request: Request,
    membership_id: str,
    action: str,
    role: str | None = None,
    permission: str | None = None,
    enabled: bool | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _admin_membership(db, user, membership_id)
    action_definition = _ADMIN_ACTIONS.get(action)
    if membership is None or action_definition is None:
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if action == "change-role" and role not in DEFAULT_ROLE_BUNDLES:
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    navigation_item = None
    if action == "navigation-access":
        navigation_item = next(
            (
                item
                for item in request.app.state.registry.get_configurable_navigation()
                if item.get("required_permission") == permission
            ),
            None,
        )
        if navigation_item is None or enabled is None:
            return _auth_page(request, "auth/forbidden.html", {}, 403)
    return _auth_page(
        request,
        "auth/confirm_action.html",
        {
            "current_user": user,
            "membership": membership,
            "action": action,
            "action_definition": action_definition,
            "role": role,
            "role_definition": DEFAULT_ROLE_BUNDLES.get(role or ""),
            "permission": permission,
            "enabled": enabled,
            "navigation_item": navigation_item,
            "error": None,
        },
    )


@router.post("/admin/users/{membership_id}/confirm/{action}", response_class=HTMLResponse)
def perform_admin_action(
    request: Request,
    membership_id: str,
    action: str,
    admin_code: str = Form(...),
    confirmation: str = Form(...),
    csrf_token: str = Form(...),
    role: str | None = Form(None),
    permission: str | None = Form(None),
    enabled: bool | None = Form(None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _admin_membership(db, user, membership_id)
    action_definition = _ADMIN_ACTIONS.get(action)
    if membership is None or action_definition is None:
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if not _valid_session_csrf(user, csrf_token):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    navigation_item = None
    if action == "navigation-access":
        navigation_item = next(
            (
                item
                for item in request.app.state.registry.get_configurable_navigation()
                if item.get("required_permission") == permission
            ),
            None,
        )
    service = AuthService(db, request.app.state.settings)
    error = None
    result_title = None
    result_values = None
    try:
        if confirmation != "confirmed":
            raise ValueError("Confirm that you understand the effect of this change")
        if action == "change-role" and role not in DEFAULT_ROLE_BUNDLES:
            raise ValueError("Select a valid workspace role")
        if action == "navigation-access" and (navigation_item is None or enabled is None):
            raise ValueError("Select a registered application access entry")
        if not service.reauthenticate_administrator(
            user_id=user.user_id,
            code=admin_code,
            ip=request.client.host if request.client else "unknown",
        ):
            raise ValueError("Administrator reauthentication was not accepted")

        if action == "change-role":
            service.change_membership_role(
                membership, role_key=role or "", actor_user_id=user.user_id
            )
        elif action == "suspend":
            if membership.user_id == user.user_id:
                raise ValueError("Use another administrator account to suspend your own account")
            service.set_membership_status(
                membership, status="suspended", actor_user_id=user.user_id
            )
        elif action == "reactivate":
            service.set_membership_status(
                membership, status="active", actor_user_id=user.user_id
            )
        elif action == "revoke-sessions":
            count = service.revoke_membership_sessions(
                membership, actor_user_id=user.user_id
            )
            result_title = "Sessions revoked"
            result_values = [f"{count} active session(s) were revoked."]
        elif action == "reenroll":
            enrollment = service.begin_reenrollment(
                membership, actor_user_id=user.user_id
            )
            result_title = "New enrollment link"
            result_values = [
                str(request.base_url).rstrip("/") + f"/auth/enroll/{enrollment.token}"
            ]
        elif action == "recovery-codes":
            result_values = service.regenerate_recovery_codes(
                membership.user_id,
                actor_user_id=user.user_id,
                operation_source="admin_panel",
            )
            result_title = "Replacement recovery codes"
        else:
            service.set_membership_permission(
                membership=membership,
                permission=permission or "",
                enabled=bool(enabled),
                actor_user_id=user.user_id,
                registered_permissions=frozenset(request.app.state.registry.all_permissions),
            )
    except ValueError as exc:
        error = str(exc)
        AuditService(db).record(
            event_type="auth.admin.operation_failed",
            outcome="FAILED",
            organization_id=membership.organization_id,
            actor_user_id=user.user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"action": action, "reason": error},
        )

    if error:
        return _auth_page(
            request,
            "auth/confirm_action.html",
            {
                "current_user": user,
                "membership": membership,
                "action": action,
                "action_definition": action_definition,
                "role": role,
                "role_definition": DEFAULT_ROLE_BUNDLES.get(role or ""),
                "permission": permission,
                "enabled": enabled,
                "navigation_item": navigation_item,
                "error": error,
            },
            400,
        )
    if result_values is not None:
        return _auth_page(
            request,
            "auth/admin_result.html",
            {
                "current_user": user,
                "membership": membership,
                "result_title": result_title,
                "result_values": result_values,
                "is_secret": action in {"reenroll", "recovery-codes"},
            },
        )
    return RedirectResponse(
        f"/auth/admin/users/{membership_id}", status_code=303
    )
