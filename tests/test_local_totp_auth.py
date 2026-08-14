"""Security-focused tests for invite-only local TOTP authentication."""

from __future__ import annotations

import re
import json
from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.platform.audit.models import AuditEvent
from app.platform.auth.models import AuthSession, Credential, EnrollmentToken, RecoveryCode
from app.platform.auth.service import AuthService
from app.settings import Settings


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        profile="test",
        auth_enabled=True,
        app_name="MEAP Test",
        session_hmac_key="test-session-key-that-is-independent",
        token_hmac_key="test-token-key-that-is-independent",
        credential_encryption_key="4G9HkM4pV4C2u_uMaY-7z8s8Q-OHN34JOj0H6jOO1V0=",
        credential_encryption_key_id="test-v1",
    )


def bootstrap_and_enroll(db_session, auth_settings):
    service = AuthService(db_session, auth_settings)
    issued = service.bootstrap_admin(
        email="alice@company.com",
        display_name="Alice Admin",
        organization_name="Example Company",
    )
    enrollment = service.get_enrollment(issued.token)
    assert enrollment is not None
    secret = service._decrypt(
        enrollment.encrypted_totp_secret,
        enrollment.nonce,
        aad=f"enrollment:{enrollment.enrollment_id}",
    )
    code = pyotp.TOTP(secret).now()
    membership, recovery_codes = service.confirm_enrollment(issued.token, code)
    return service, membership, secret, recovery_codes


def invite_and_enroll(service, administrator, *, email, role="operator"):
    issued = service.invite_user(
        organization_id=administrator.organization_id,
        email=email,
        display_name=email.split("@", 1)[0].title(),
        role=role,
        actor_user_id=administrator.user_id,
    )
    enrollment = service.get_enrollment(issued.token)
    assert enrollment is not None
    secret = service._decrypt(
        enrollment.encrypted_totp_secret,
        enrollment.nonce,
        aad=f"enrollment:{enrollment.enrollment_id}",
    )
    membership, recovery_codes = service.confirm_enrollment(
        issued.token, pyotp.TOTP(secret).now()
    )
    return membership, secret, recovery_codes


def test_bootstrap_is_database_guarded_and_secret_is_encrypted(db_session, auth_settings):
    service = AuthService(db_session, auth_settings)
    issued = service.bootstrap_admin(
        email="alice@company.com",
        display_name="Alice",
        organization_name="Example",
    )
    enrollment = db_session.scalar(select(EnrollmentToken))
    assert enrollment is not None
    assert issued.token.encode() not in enrollment.encrypted_totp_secret
    assert enrollment.token_hmac != issued.token
    with pytest.raises(ValueError, match="already been initiated"):
        service.bootstrap_admin(
            email="mallory@company.com",
            display_name="Mallory",
            organization_name="Other",
        )


def test_enrollment_is_single_use_and_issues_recovery_codes(db_session, auth_settings):
    service, membership, _secret, recovery_codes = bootstrap_and_enroll(db_session, auth_settings)
    assert membership.status == "active"
    assert len(recovery_codes) == 10
    assert db_session.scalar(select(Credential)).encrypted_secret
    assert db_session.scalars(select(RecoveryCode)).all()
    enrollment = db_session.scalar(select(EnrollmentToken))
    assert service.get_enrollment("not-the-token") is None
    assert enrollment.consumed_at is not None


def test_totp_replay_is_rejected_and_recovery_code_is_single_use(db_session, auth_settings):
    service, membership, secret, recovery_codes = bootstrap_and_enroll(db_session, auth_settings)
    next_counter = int(datetime.now(timezone.utc).timestamp()) // 30 + 1
    next_code = pyotp.TOTP(secret).at(next_counter * 30)
    first = service.authenticate(
        email=membership.user.email,
        code=next_code,
        ip="127.0.0.1",
        user_agent="pytest",
    )
    assert first is not None
    replay = service.authenticate(
        email=membership.user.email,
        code=next_code,
        ip="127.0.0.2",
        user_agent="pytest",
    )
    assert replay is None

    recovery = recovery_codes[0]
    recovered = service.authenticate(
        email=membership.user.email,
        code=recovery,
        ip="127.0.0.3",
        user_agent="pytest",
    )
    assert recovered is not None and recovered.used_recovery_code
    reused = service.authenticate(
        email=membership.user.email,
        code=recovery,
        ip="127.0.0.4",
        user_agent="pytest",
    )
    assert reused is None


def test_regenerating_recovery_codes_invalidates_every_old_code(db_session, auth_settings):
    service, membership, _secret, old_codes = bootstrap_and_enroll(db_session, auth_settings)
    new_codes = service.regenerate_recovery_codes(membership.user_id)
    assert len(new_codes) == 10
    assert service.authenticate(
        email=membership.user.email,
        code=old_codes[0],
        ip="127.0.0.10",
        user_agent="pytest",
    ) is None
    replacement = service.authenticate(
        email=membership.user.email,
        code=new_codes[0],
        ip="127.0.0.11",
        user_agent="pytest",
    )
    assert replacement is not None and replacement.used_recovery_code


def test_sensitive_admin_actions_require_fresh_reauthentication(db_session, auth_settings):
    service, administrator, _secret, recovery_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    login = service.authenticate(
        email=administrator.user.email,
        code=recovery_codes[0],
        ip="127.0.0.1",
        user_agent="pytest",
    )
    assert login is not None
    assert not service.administrator_reauthentication_is_current(
        login.session.session_id
    )
    assert service.reauthenticate_administrator(
        user_id=administrator.user_id,
        code=recovery_codes[1],
        ip="127.0.0.1",
        session_id=login.session.session_id,
    )
    assert service.administrator_reauthentication_is_current(
        login.session.session_id
    )
    assert not service.reauthenticate_administrator(
        user_id=administrator.user_id,
        code=recovery_codes[1],
        ip="127.0.0.1",
        session_id=login.session.session_id,
    )
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.event_type == "auth.admin.reauthenticated"
        )
    ).all()
    assert len(events) == 1


def test_last_active_administrator_cannot_be_removed_or_reset(db_session, auth_settings):
    service, administrator, _secret, _codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    with pytest.raises(ValueError, match="retain at least one"):
        service.change_membership_role(
            administrator,
            role_key="operator",
            actor_user_id="another-administrator",
        )
    with pytest.raises(ValueError, match="retain at least one"):
        service.set_membership_status(
            administrator,
            status="suspended",
            actor_user_id="another-administrator",
        )
    with pytest.raises(ValueError, match="retain at least one"):
        service.begin_reenrollment(
            administrator,
            actor_user_id="another-administrator",
        )
    assert administrator.status == "active"
    assert administrator.role == "workspace_admin"


def test_administrator_cannot_apply_self_defeating_lifecycle_actions(
    db_session, auth_settings
):
    service, administrator, _secret, _codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    with pytest.raises(ValueError, match="Another administrator"):
        service.change_membership_role(
            administrator,
            role_key="operator",
            actor_user_id=administrator.user_id,
        )
    with pytest.raises(ValueError, match="Another administrator"):
        service.set_membership_status(
            administrator,
            status="suspended",
            actor_user_id=administrator.user_id,
        )
    with pytest.raises(ValueError, match="Another administrator"):
        service.begin_reenrollment(
            administrator,
            actor_user_id=administrator.user_id,
        )


def test_role_change_and_suspension_revoke_sessions_immediately(db_session, auth_settings):
    service, administrator, _admin_secret, _admin_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    member, _secret, member_codes = invite_and_enroll(
        service, administrator, email="bob@company.com"
    )
    login = service.authenticate(
        email=member.user.email,
        code=member_codes[0],
        ip="127.0.0.2",
        user_agent="pytest",
    )
    assert login is not None
    service.change_membership_role(
        member, role_key="analyst", actor_user_id=administrator.user_id
    )
    db_session.refresh(login.session)
    assert db_session.get(AuthSession, login.session.session_id).revoked_at is not None

    second_login = service.authenticate(
        email=member.user.email,
        code=member_codes[1],
        ip="127.0.0.3",
        user_agent="pytest",
    )
    assert second_login is not None
    service.set_membership_status(
        member, status="suspended", actor_user_id=administrator.user_id
    )
    assert member.status == "suspended"
    db_session.refresh(second_login.session)
    assert db_session.get(AuthSession, second_login.session.session_id).revoked_at is not None
    service.set_membership_status(
        member, status="active", actor_user_id=administrator.user_id
    )
    assert member.status == "active"


def test_reenrollment_invalidates_old_credentials_codes_and_sessions(db_session, auth_settings):
    service, administrator, _admin_secret, _admin_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    member, _secret, member_codes = invite_and_enroll(
        service, administrator, email="bob@company.com"
    )
    login = service.authenticate(
        email=member.user.email,
        code=member_codes[0],
        ip="127.0.0.4",
        user_agent="pytest",
    )
    assert login is not None
    issued = service.begin_reenrollment(
        member, actor_user_id=administrator.user_id
    )
    assert member.status == "pending"
    assert service.get_enrollment(issued.token) is not None
    db_session.refresh(login.session)
    assert db_session.get(AuthSession, login.session.session_id).revoked_at is not None
    assert db_session.scalar(
        select(Credential).where(
            Credential.user_id == member.user_id,
            Credential.revoked_at.is_(None),
        )
    ) is None
    assert db_session.scalars(
        select(RecoveryCode).where(RecoveryCode.user_id == member.user_id)
    ).all() == []


def test_domain_allowlist_restricts_admin_asserted_invites(db_session, auth_settings):
    settings = auth_settings.model_copy(update={"allowed_email_domains": "company.com"})
    service = AuthService(db_session, settings)
    with pytest.raises(ValueError, match="domain"):
        service.bootstrap_admin(
            email="alice@outside.example",
            display_name="Alice",
            organization_name="Example",
        )


def test_versioned_credential_keyring_can_decrypt_an_old_key(db_session, auth_settings):
    old_key = auth_settings.credential_encryption_key
    old_settings = auth_settings.model_copy(update={
        "credential_encryption_keys": json.dumps({"v1": old_key}),
        "credential_encryption_key_id": "v1",
    })
    old_service = AuthService(db_session, old_settings)
    ciphertext, nonce = old_service._encrypt("shared-secret", aad="credential:test:totp")
    new_key = "SRG0wL8LxFvHwbG_vu2lA8Bqv8D6Zrmkx1r4qZ9xDRY="
    rotated = old_settings.model_copy(update={
        "credential_encryption_keys": json.dumps({"v1": old_key, "v2": new_key}),
        "credential_encryption_key_id": "v2",
    })
    assert AuthService(db_session, rotated)._decrypt(
        ciphertext,
        nonce,
        aad="credential:test:totp",
        key_id="v1",
    ) == "shared-secret"


def test_auth_enabled_redirects_anonymous_requests(db_engine, auth_settings, monkeypatch):
    import app.main as main_module
    import app.platform.database.base as db_base

    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    app = main_module.create_app()
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/auth/login?next=/")
        login = client.get("/auth/login")
        assert login.status_code == 200
        assert "Sign in to MEAP Test" in login.text


def test_login_rejects_a_tampered_signed_form_token(db_engine, auth_settings, monkeypatch):
    import app.main as main_module
    import app.platform.database.base as db_base

    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    app = main_module.create_app()
    with TestClient(app) as client:
        login = client.get("/auth/login")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', login.text).group(1)
        response = client.post(
            "/auth/login",
            data={
                "csrf_token": csrf + "tampered",
                "email": "nobody@example.com",
                "code": "000000",
                "next": "/",
            },
        )
        assert response.status_code == 403
        assert "sign-in form expired" in response.text


def test_complete_enrollment_login_and_logout_flow(
    db_engine, db_session, auth_settings, monkeypatch
):
    import app.main as main_module
    import app.platform.database.base as db_base

    service = AuthService(db_session, auth_settings)
    issued = service.bootstrap_admin(
        email="alice@company.com",
        display_name="Alice Admin",
        organization_name="Example Company",
    )
    enrollment = service.get_enrollment(issued.token)
    assert enrollment is not None
    secret = service._decrypt(
        enrollment.encrypted_totp_secret,
        enrollment.nonce,
        aad=f"enrollment:{enrollment.enrollment_id}",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    db_session.close()
    app = main_module.create_app()
    with TestClient(app) as client:
        page = client.get(f"/auth/enroll/{issued.token}")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        # Opening the login page in another tab must not invalidate enrollment.
        assert client.get("/auth/login").status_code == 200
        enrolled = client.post(
            f"/auth/enroll/{issued.token}",
            data={"csrf_token": csrf, "code": pyotp.TOTP(secret).now()},
        )
        assert enrolled.status_code == 200
        assert "Save your recovery codes" in enrolled.text

        login_page = client.get("/auth/login")
        login_csrf = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)
        next_counter = int(datetime.now(timezone.utc).timestamp()) // 30 + 1
        response = client.post(
            "/auth/login",
            data={
                "csrf_token": login_csrf,
                "email": "alice@company.com",
                "code": pyotp.TOTP(secret).at(next_counter * 30),
                "next": "/",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "meap_session" in client.cookies
        workspace = client.get("/")
        assert workspace.status_code == 200
        assert "Alice Admin" in workspace.text
        session_csrf = re.search(r'name="csrf_token" value="([^"]+)"', workspace.text).group(1)
        logged_out = client.post(
            "/auth/logout",
            data={"csrf_token": session_csrf},
            follow_redirects=False,
        )
        assert logged_out.status_code == 303
        assert "meap_session" not in client.cookies


def test_navigation_deny_hides_link_and_blocks_direct_route(
    db_engine, db_session, auth_settings, monkeypatch
):
    import app.main as main_module
    import app.platform.database.base as db_base
    from app.modules.bank_reconciliation.permissions import BANK_RECON_VIEW

    service, membership, _secret, recovery_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    service.set_membership_permission(
        membership=membership,
        permission=BANK_RECON_VIEW,
        enabled=False,
        actor_user_id=membership.user_id,
        registered_permissions=frozenset(
            permission
            for module in main_module.MODULES
            for permission in module.permissions
        ),
    )

    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    db_session.close()
    app = main_module.create_app()
    with TestClient(app) as client:
        login_page = client.get("/auth/login")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)
        signed_in = client.post(
            "/auth/login",
            data={
                "csrf_token": csrf,
                "email": "alice@company.com",
                "code": recovery_codes[0],
                "next": "/",
            },
            follow_redirects=False,
        )
        assert signed_in.status_code == 303

        workspace = client.get("/")
        assert workspace.status_code == 200
        assert 'href="/bank-recon"' not in workspace.text

        direct = client.get("/bank-recon")
        assert direct.status_code == 403


def test_developer_diagnostics_are_hidden_and_denied_for_non_admin(
    db_engine, db_session, auth_settings, monkeypatch
):
    import app.main as main_module
    import app.platform.database.base as db_base

    service, administrator, _admin_secret, _admin_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    operator, _secret, recovery_codes = invite_and_enroll(
        service, administrator, email="operator@company.com", role="operator"
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    db_session.close()
    app = main_module.create_app()
    with TestClient(app) as client:
        login_page = client.get("/auth/login")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)
        signed_in = client.post(
            "/auth/login",
            data={
                "csrf_token": csrf,
                "email": operator.user.email,
                "code": recovery_codes[0],
                "next": "/",
            },
            follow_redirects=False,
        )
        assert signed_in.status_code == 303

        workspace = client.get("/")
        assert workspace.status_code == 200
        assert 'href="/developer"' not in workspace.text
        assert "Developer diagnostics" not in workspace.text
        assert client.get("/developer").status_code == 403
        assert client.get("/developer/api/modules").status_code == 403
        assert client.get("/developer/health").status_code == 200


def test_admin_account_panel_requires_reauthentication_for_recovery_rotation(
    db_engine, db_session, auth_settings, monkeypatch
):
    import app.main as main_module
    import app.platform.database.base as db_base

    _service, membership, _secret, recovery_codes = bootstrap_and_enroll(
        db_session, auth_settings
    )
    membership_id = membership.membership_id
    monkeypatch.setattr(main_module, "get_settings", lambda: auth_settings)
    monkeypatch.setattr(db_base, "make_engine", lambda url=None: db_engine)
    db_session.close()
    app = main_module.create_app()
    with TestClient(app) as client:
        login_page = client.get("/auth/login")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)
        signed_in = client.post(
            "/auth/login",
            data={
                "csrf_token": csrf,
                "email": "alice@company.com",
                "code": recovery_codes[0],
                "next": "/auth/admin/users",
            },
            follow_redirects=False,
        )
        assert signed_in.status_code == 303

        users = client.get("/auth/admin/users")
        assert users.status_code == 200
        assert "Users and memberships" in users.text
        assert "Manage" in users.text
        workspace = client.get("/")
        assert 'href="/developer"' in workspace.text
        assert client.get("/developer").status_code == 200

        disabled = client.post(
            f"/auth/admin/users/{membership_id}/navigation-access",
            data={
                "csrf_token": re.search(
                    r'name="csrf_token" value="([^"]+)"', users.text
                ).group(1),
                "permission": "bank_reconciliation.reconciliation.view",
                "enabled": "false",
            },
            follow_redirects=False,
        )
        assert disabled.status_code == 303
        assert client.get("/bank-recon").status_code == 403

        detail = client.get(f"/auth/admin/users/{membership_id}")
        assert detail.status_code == 200
        assert "Personal recovery" in detail.text
        assert "Unused backup sign-in codes" in detail.text
        assert "Another workspace administrator must change your role" in detail.text
        assert "Suspend account" not in detail.text
        assert "Reset and re-enroll authenticator" not in detail.text
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", detail.text)

        confirmation = client.get(
            f"/auth/admin/users/{membership_id}/confirm/recovery-codes"
        )
        assert confirmation.status_code == 200
        assert "Confirm recovery-code replacement" in confirmation.text
        session_csrf = re.search(
            r'name="csrf_token" value="([^"]+)"', confirmation.text
        ).group(1)
        replaced = client.post(
            f"/auth/admin/users/{membership_id}/confirm/recovery-codes",
            data={
                "csrf_token": session_csrf,
                "admin_code": recovery_codes[1],
                "confirmation": "confirmed",
            },
        )
        assert replaced.status_code == 200
        assert "Replacement recovery codes" in replaced.text
        assert "displayed again" in replaced.text

        verified_confirmation = client.get(
            f"/auth/admin/users/{membership_id}/confirm/recovery-codes"
        )
        assert "No additional code is needed" in verified_confirmation.text
        assert 'name="admin_code"' not in verified_confirmation.text
