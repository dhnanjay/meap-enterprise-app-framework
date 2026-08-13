"""Security-focused tests for invite-only local TOTP authentication."""

from __future__ import annotations

import re
import json
from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.platform.auth.models import Credential, EnrollmentToken, RecoveryCode
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
