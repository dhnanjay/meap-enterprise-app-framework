"""HTML routes for local TOTP enrollment, login, logout, and administration."""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.middleware.authentication import session_cookie_name
from app.platform.audit.service import AuditService
from app.platform.auth.context import UserContext, get_current_user
from app.platform.auth.models import AuthSession, Membership
from app.platform.auth.service import AuthService, now_utc
from app.platform.database.session import get_db
from app.platform.templates.rendering import templates

router = APIRouter(prefix="/auth", tags=["authentication"])
FORM_CSRF_COOKIE = "meap_auth_form_csrf"


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


def _set_form_csrf(response: HTMLResponse, request: Request, token: str) -> None:
    response.set_cookie(
        FORM_CSRF_COOKIE,
        token,
        httponly=True,
        secure=request.app.state.settings.profile == "production",
        samesite="lax",
        path="/auth",
        max_age=900,
    )


def _valid_form_csrf(request: Request, submitted: str) -> bool:
    cookie = request.cookies.get(FORM_CSRF_COOKIE, "")
    return bool(cookie and submitted and hmac.compare_digest(cookie, submitted))


def _safe_next(value: str) -> str:
    parsed = urlparse(value)
    return value if value.startswith("/") and not parsed.netloc and not value.startswith("//") else "/"


def _valid_session_csrf(user: UserContext, submitted: str) -> bool:
    return bool(user.csrf_token and submitted and hmac.compare_digest(user.csrf_token, submitted))


@router.get("/login", response_class=HTMLResponse, name="auth.login")
def login_page(request: Request, next: str = "/"):
    if getattr(request.state, "user", None):
        return RedirectResponse(_safe_next(next), status_code=303)
    csrf = secrets.token_urlsafe(24)
    response = _auth_page(
        request,
        "auth/login.html",
        {"csrf_token": csrf, "next_path": _safe_next(next), "error": None},
    )
    _set_form_csrf(response, request, csrf)
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
    if not _valid_form_csrf(request, csrf_token):
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
    response.delete_cookie(FORM_CSRF_COOKIE, path="/auth")
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
    csrf = secrets.token_urlsafe(24)
    response = _auth_page(request, "auth/enroll.html", {
        "token": token,
        "csrf_token": csrf,
        "qr_data_uri": service.enrollment_qr_data_uri(enrollment),
        "membership": enrollment.membership,
        "error": None,
    })
    _set_form_csrf(response, request, csrf)
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
    if not _valid_form_csrf(request, csrf_token):
        error = "The enrollment form expired. Refresh and try again."
    else:
        try:
            membership, recovery_codes = service.confirm_enrollment(token, code)
            response = _auth_page(request, "auth/recovery_codes.html", {
                "membership": membership,
                "recovery_codes": recovery_codes,
            })
            response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            response.delete_cookie(FORM_CSRF_COOKIE, path="/auth")
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
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    memberships = db.scalars(
        select(Membership).where(Membership.organization_id == user.organization_id).order_by(Membership.created_at)
    ).all()
    return _auth_page(request, "auth/users.html", {
        "current_user": user,
        "memberships": memberships,
        "invite_url": None,
        "error": None,
    })


@router.post("/admin/users/invite", response_class=HTMLResponse)
def invite_user(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    role: str = Form("member"),
    csrf_token: str = Form(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if not _valid_session_csrf(user, csrf_token):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    service = AuthService(db, request.app.state.settings)
    error = None
    invite_url = None
    try:
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
    memberships = db.scalars(
        select(Membership).where(Membership.organization_id == user.organization_id).order_by(Membership.created_at)
    ).all()
    return _auth_page(request, "auth/users.html", {
        "current_user": user,
        "memberships": memberships,
        "invite_url": invite_url,
        "error": error,
    }, 400 if error else 200)


@router.post("/admin/users/{membership_id}/suspend")
def suspend_user(
    request: Request,
    membership_id: str,
    csrf_token: str = Form(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = db.get(Membership, membership_id)
    if user.role != "admin" or membership is None or membership.organization_id != user.organization_id:
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if not _valid_session_csrf(user, csrf_token):
        return _auth_page(request, "auth/forbidden.html", {}, 403)
    if membership.user_id == user.user_id:
        return RedirectResponse("/auth/admin/users?error=cannot-suspend-self", status_code=303)
    membership.status = "suspended"
    membership.suspended_at = now_utc()
    db.execute(
        update(AuthSession)
        .where(AuthSession.membership_id == membership_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now_utc())
    )
    AuditService(db).record(
        event_type="auth.membership.suspended",
        organization_id=membership.organization_id,
        actor_user_id=user.user_id,
        entity_type="membership",
        entity_id=membership.membership_id,
        event_data={"subject_user_id": membership.user_id},
        commit=False,
    )
    db.commit()
    return RedirectResponse("/auth/admin/users", status_code=303)
