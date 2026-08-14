"""Local, invite-only TOTP authentication services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.platform.audit.service import AuditService
from app.platform.auth.models import (
    AccessRole,
    AuthSession,
    BootstrapState,
    Credential,
    EnrollmentToken,
    LoginThrottle,
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    RecoveryCode,
    RolePermission,
    User,
)
from app.platform.permissions.roles import DEFAULT_ROLE_BUNDLES, expand_permission_patterns
from app.settings import Settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    return slug or "organization"


@dataclass(frozen=True)
class EnrollmentResult:
    token: str
    enrollment: EnrollmentToken


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    session: AuthSession
    used_recovery_code: bool = False


class AuthService:
    """Own credential cryptography and transactional authentication state."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _token_hmac(self, value: str) -> str:
        return hmac.new(
            self.settings.token_hmac_key.encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    def _session_hmac(self, value: str) -> str:
        return hmac.new(
            self.settings.session_hmac_key.encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    def _encryption_key(self, key_id: str | None = None) -> bytes:
        selected_id = key_id or self.settings.credential_encryption_key_id
        encoded_key = self.settings.credential_encryption_key
        if self.settings.credential_encryption_keys:
            try:
                keyring = json.loads(self.settings.credential_encryption_keys)
                encoded_key = keyring[selected_id]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RuntimeError(f"No valid credential encryption key for {selected_id}") from exc
        elif selected_id != self.settings.credential_encryption_key_id:
            raise RuntimeError(f"Credential encryption key {selected_id} is unavailable")
        try:
            key = base64.urlsafe_b64decode(encoded_key)
        except Exception as exc:
            raise RuntimeError("MEAP credential encryption key is not valid base64") from exc
        if len(key) != 32:
            raise RuntimeError("MEAP credential encryption key must decode to 32 bytes")
        return key

    def _encrypt(self, plaintext: str, *, aad: str) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._encryption_key()).encrypt(
            nonce, plaintext.encode(), aad.encode()
        )
        return ciphertext, nonce

    def _decrypt(self, ciphertext: bytes, nonce: bytes, *, aad: str, key_id: str | None = None) -> str:
        return AESGCM(self._encryption_key(key_id)).decrypt(
            nonce, ciphertext, aad.encode()
        ).decode()

    def validate_invited_email(self, email: str) -> str:
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            raise ValueError("Enter a valid email address")
        allowed = {
            domain.strip().casefold()
            for domain in self.settings.allowed_email_domains.split(",")
            if domain.strip()
        }
        if allowed and normalized.rsplit("@", 1)[1] not in allowed:
            raise ValueError("That email domain is not allowed for this deployment")
        return normalized

    def ensure_default_roles(self, organization_id: str) -> dict[str, AccessRole]:
        existing = {
            role.role_key: role
            for role in self.db.scalars(
                select(AccessRole).where(AccessRole.organization_id == organization_id)
            ).all()
        }
        for role_key, definition in DEFAULT_ROLE_BUNDLES.items():
            if role_key in existing:
                continue
            role = AccessRole(
                organization_id=organization_id,
                role_key=role_key,
                display_name=str(definition["display_name"]),
                description=str(definition["description"]),
                is_system=True,
            )
            role.permission_grants = [
                RolePermission(permission_pattern=pattern)
                for pattern in definition["patterns"]
            ]
            self.db.add(role)
            existing[role_key] = role
        self.db.flush()
        return existing

    def assign_role(
        self,
        membership: Membership,
        role_key: str,
        *,
        assigned_by_user_id: str | None,
    ) -> AccessRole:
        roles = self.ensure_default_roles(membership.organization_id)
        role = roles.get(role_key)
        if role is None:
            raise ValueError("Unknown workspace role")
        self.db.execute(
            delete(MembershipRole).where(MembershipRole.membership_id == membership.membership_id)
        )
        self.db.add(
            MembershipRole(
                membership_id=membership.membership_id,
                role_id=role.role_id,
                assigned_by_user_id=assigned_by_user_id,
            )
        )
        membership.role = role_key
        self.db.flush()
        return role

    def permissions_for_membership(
        self, membership_id: str, registered_permissions: frozenset[str]
    ) -> tuple[frozenset[str], tuple[str, ...]]:
        assignments = self.db.scalars(
            select(MembershipRole).where(MembershipRole.membership_id == membership_id)
        ).all()
        if not assignments:
            membership = self.db.get(Membership, membership_id)
            if membership is not None:
                legacy_role = {
                    "admin": "workspace_admin",
                    "member": "operator",
                }.get(membership.role, membership.role)
                self.assign_role(
                    membership,
                    legacy_role if legacy_role in DEFAULT_ROLE_BUNDLES else "viewer",
                    assigned_by_user_id=None,
                )
                self.db.commit()
                assignments = self.db.scalars(
                    select(MembershipRole).where(MembershipRole.membership_id == membership_id)
                ).all()
        patterns = frozenset(
            grant.permission_pattern
            for assignment in assignments
            for grant in assignment.role.permission_grants
        )
        role_keys = tuple(sorted({assignment.role.role_key for assignment in assignments}))
        resolved = set(expand_permission_patterns(patterns, registered_permissions))
        overrides = self.db.scalars(
            select(MembershipPermission).where(
                MembershipPermission.membership_id == membership_id
            )
        ).all()
        for override in overrides:
            if override.permission not in registered_permissions:
                continue
            if override.effect == "allow":
                resolved.add(override.permission)
            elif override.effect == "deny":
                resolved.discard(override.permission)
        return frozenset(resolved), role_keys

    def set_membership_permission(
        self,
        *,
        membership: Membership,
        permission: str,
        enabled: bool,
        actor_user_id: str,
        registered_permissions: frozenset[str],
    ) -> None:
        if permission not in registered_permissions:
            raise ValueError("Permission is not registered")
        current_permissions, _ = self.permissions_for_membership(
            membership.membership_id, registered_permissions
        )
        baseline_enabled = permission in current_permissions
        existing = self.db.scalar(
            select(MembershipPermission).where(
                MembershipPermission.membership_id == membership.membership_id,
                MembershipPermission.permission == permission,
            )
        )
        desired_effect = "allow" if enabled else "deny"
        if existing is None:
            existing = MembershipPermission(
                membership_id=membership.membership_id,
                permission=permission,
                effect=desired_effect,
                assigned_by_user_id=actor_user_id,
            )
            self.db.add(existing)
        else:
            existing.effect = desired_effect
            existing.assigned_by_user_id = actor_user_id
            existing.assigned_at = now_utc()
        AuditService(self.db).record(
            event_type="auth.membership.permission_changed",
            organization_id=membership.organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={
                "permission": permission,
                "enabled": enabled,
                "previously_enabled": baseline_enabled,
            },
            commit=False,
        )
        self.db.commit()

    def issue_enrollment(
        self,
        membership: Membership,
        *,
        created_by_user_id: str | None,
        enforce_admission: bool = True,
    ) -> EnrollmentResult:
        if enforce_admission and self.settings.admission_mode == "disabled":
            raise ValueError("New memberships are disabled")
        self.db.execute(
            update(EnrollmentToken)
            .where(
                EnrollmentToken.membership_id == membership.membership_id,
                EnrollmentToken.consumed_at.is_(None),
            )
            .values(consumed_at=now_utc())
        )
        enrollment_id = str(uuid.uuid4())
        secret = pyotp.random_base32(length=32)
        ciphertext, nonce = self._encrypt(secret, aad=f"enrollment:{enrollment_id}")
        raw_token = secrets.token_urlsafe(32)
        enrollment = EnrollmentToken(
            enrollment_id=enrollment_id,
            membership_id=membership.membership_id,
            token_hmac=self._token_hmac(raw_token),
            encrypted_totp_secret=ciphertext,
            nonce=nonce,
            encryption_key_id=self.settings.credential_encryption_key_id,
            expires_at=now_utc() + timedelta(minutes=self.settings.enrollment_lifetime_minutes),
            created_by_user_id=created_by_user_id,
        )
        self.db.add(enrollment)
        self.db.flush()
        return EnrollmentResult(raw_token, enrollment)

    def bootstrap_admin(
        self, *, email: str, display_name: str, organization_name: str
    ) -> EnrollmentResult:
        if self.db.get(BootstrapState, "initial_admin") is not None:
            raise ValueError("Initial administrator bootstrap has already been initiated")
        normalized = self.validate_invited_email(email)
        organization = Organization(name=organization_name, slug=safe_slug(organization_name))
        user = User(
            email=email.strip(),
            normalized_email=normalized,
            display_name=display_name.strip() or normalized,
            asserted_by_user_id=None,
        )
        membership = Membership(
            organization=organization,
            user=user,
            role="admin",
            status="pending",
        )
        self.db.add_all([organization, user, membership])
        self.db.flush()
        self.assign_role(membership, "workspace_admin", assigned_by_user_id=None)
        result = self.issue_enrollment(membership, created_by_user_id=None)
        self.db.add(
            BootstrapState(
                marker="initial_admin",
                administrator_user_id=user.user_id,
            )
        )
        AuditService(self.db).record(
            event_type="auth.bootstrap.initiated",
            organization_id=organization.organization_id,
            entity_type="user",
            entity_id=user.user_id,
            event_data={"identity_assurance": "admin_asserted"},
            commit=False,
        )
        self.db.commit()
        return result

    def invite_user(
        self,
        *,
        organization_id: str,
        email: str,
        display_name: str,
        role: str,
        actor_user_id: str,
    ) -> EnrollmentResult:
        normalized = self.validate_invited_email(email)
        if role == "admin":
            role = "workspace_admin"
        elif role == "member":
            role = "operator"
        if role not in DEFAULT_ROLE_BUNDLES:
            raise ValueError("Unknown workspace role")
        user = self.db.scalar(select(User).where(User.normalized_email == normalized))
        if user is None:
            user = User(
                email=email.strip(),
                normalized_email=normalized,
                display_name=display_name.strip() or normalized,
                asserted_by_user_id=actor_user_id,
            )
            self.db.add(user)
            self.db.flush()
        else:
            other_membership = self.db.scalar(
                select(Membership).where(
                    Membership.user_id == user.user_id,
                    Membership.organization_id != organization_id,
                )
            )
            if other_membership is not None:
                raise ValueError("Multiple organization memberships are not enabled in this release")
        membership = self.db.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user.user_id,
            )
        )
        if membership is None:
            membership = Membership(
                organization_id=organization_id,
                user_id=user.user_id,
                role=role,
                status="pending",
                created_by_user_id=actor_user_id,
            )
            self.db.add(membership)
            self.db.flush()
        elif membership.status == "active":
            raise ValueError("That user already has an active membership")
        else:
            membership.role = role
            membership.status = "pending"
        self.assign_role(membership, role, assigned_by_user_id=actor_user_id)
        result = self.issue_enrollment(membership, created_by_user_id=actor_user_id)
        AuditService(self.db).record(
            event_type="auth.membership.invited",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"role": role, "identity_assurance": "admin_asserted"},
            commit=False,
        )
        self.db.commit()
        return result

    def get_enrollment(self, raw_token: str) -> EnrollmentToken | None:
        enrollment = self.db.scalar(
            select(EnrollmentToken).where(
                EnrollmentToken.token_hmac == self._token_hmac(raw_token),
                EnrollmentToken.consumed_at.is_(None),
            )
        )
        if enrollment is None or aware(enrollment.expires_at) <= now_utc():
            return None
        return enrollment

    def enrollment_qr_data_uri(self, enrollment: EnrollmentToken) -> str:
        secret = self._decrypt(
            enrollment.encrypted_totp_secret,
            enrollment.nonce,
            aad=f"enrollment:{enrollment.enrollment_id}",
            key_id=enrollment.encryption_key_id,
        )
        user = enrollment.membership.user
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=self.settings.app_name,
        )
        image = qrcode.make(uri)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()

    def confirm_enrollment(self, raw_token: str, code: str) -> tuple[Membership, list[str]]:
        enrollment = self.get_enrollment(raw_token)
        if enrollment is None:
            raise ValueError("This enrollment link is invalid or has expired")
        secret = self._decrypt(
            enrollment.encrypted_totp_secret,
            enrollment.nonce,
            aad=f"enrollment:{enrollment.enrollment_id}",
            key_id=enrollment.encryption_key_id,
        )
        matched_counter = self._matching_counter(secret, code)
        if matched_counter is None:
            raise ValueError("The authentication code is not valid")
        credential_id = str(uuid.uuid4())
        ciphertext, nonce = self._encrypt(secret, aad=f"credential:{credential_id}:totp")
        self.db.execute(
            update(Credential)
            .where(Credential.user_id == enrollment.membership.user_id, Credential.revoked_at.is_(None))
            .values(revoked_at=now_utc())
        )
        credential = Credential(
            credential_id=credential_id,
            user_id=enrollment.membership.user_id,
            encrypted_secret=ciphertext,
            nonce=nonce,
            encryption_key_id=self.settings.credential_encryption_key_id,
            last_accepted_counter=matched_counter,
        )
        enrollment.consumed_at = now_utc()
        membership = enrollment.membership
        membership.status = "active"
        membership.activated_at = now_utc()
        self.db.add(credential)
        recovery_codes = self._replace_recovery_codes(membership.user_id)
        bootstrap = self.db.get(BootstrapState, "initial_admin")
        if bootstrap and bootstrap.administrator_user_id == membership.user_id:
            bootstrap.completed_at = now_utc()
        AuditService(self.db).record(
            event_type="auth.credential.enrolled",
            organization_id=membership.organization_id,
            actor_user_id=membership.user_id,
            entity_type="credential",
            entity_id=credential_id,
            event_data={"credential_type": "totp"},
            commit=False,
        )
        self.db.commit()
        return membership, recovery_codes

    def _replace_recovery_codes(self, user_id: str) -> list[str]:
        self.db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
        raw_codes = [secrets.token_hex(16).upper() for _ in range(10)]
        self.db.add_all(
            [RecoveryCode(user_id=user_id, code_hmac=self._token_hmac(code)) for code in raw_codes]
        )
        return ["-".join(code[index:index + 8] for index in range(0, 32, 8)) for code in raw_codes]

    def regenerate_recovery_codes(
        self,
        user_id: str,
        *,
        actor_user_id: str | None = None,
        operation_source: str = "host_cli",
    ) -> list[str]:
        """Replace every recovery code and return the replacements exactly once."""
        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            raise ValueError("Active user not found")
        codes = self._replace_recovery_codes(user_id)
        AuditService(self.db).record(
            event_type="auth.recovery_codes.regenerated",
            actor_user_id=actor_user_id or user_id,
            entity_type="user",
            entity_id=user_id,
            event_data={"operation_source": operation_source},
            commit=False,
        )
        self.db.commit()
        return codes

    def _matching_counter(self, secret: str, code: str) -> int | None:
        submitted = re.sub(r"\s+", "", code)
        current = int(now_utc().timestamp()) // 30
        totp = pyotp.TOTP(secret, interval=30)
        for counter in (current - 1, current, current + 1):
            if hmac.compare_digest(totp.at(counter * 30), submitted):
                return counter
        return None

    def _consume_user_code(self, user: User, code: str) -> tuple[bool, str | None]:
        """Validate and atomically consume a TOTP step or recovery code."""
        normalized_recovery = re.sub(r"[^A-Fa-f0-9]", "", code).upper()
        if len(normalized_recovery) == 32:
            recovery = self.db.scalar(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.user_id,
                    RecoveryCode.code_hmac == self._token_hmac(normalized_recovery),
                    RecoveryCode.consumed_at.is_(None),
                )
            )
            if recovery:
                recovery.consumed_at = now_utc()
                return True, "recovery_code"
            return False, None

        credential = self.db.scalar(
            select(Credential).where(
                Credential.user_id == user.user_id,
                Credential.credential_type == "totp",
                Credential.revoked_at.is_(None),
            )
        )
        if credential is None:
            return False, None
        secret = self._decrypt(
            credential.encrypted_secret,
            credential.nonce,
            aad=f"credential:{credential.credential_id}:totp",
            key_id=credential.encryption_key_id,
        )
        counter = self._matching_counter(secret, code)
        if counter is None:
            return False, None
        result = self.db.execute(
            update(Credential)
            .where(
                Credential.credential_id == credential.credential_id,
                or_(
                    Credential.last_accepted_counter.is_(None),
                    Credential.last_accepted_counter < counter,
                ),
            )
            .values(last_accepted_counter=counter, last_used_at=now_utc())
        )
        return result.rowcount == 1, "totp" if result.rowcount == 1 else None

    def _throttle_keys(self, email: str, ip: str) -> tuple[str, str]:
        return self._token_hmac(f"account-ip:{normalize_email(email)}:{ip}"), self._token_hmac(f"ip:{ip}")

    def _is_throttled(self, keys: tuple[str, str]) -> bool:
        moment = now_utc()
        rows = self.db.scalars(select(LoginThrottle).where(LoginThrottle.throttle_key.in_(keys))).all()
        return any(row.blocked_until and aware(row.blocked_until) > moment for row in rows)

    def _record_failure(self, keys: tuple[str, str]) -> None:
        moment = now_utc()
        for key, limit in ((keys[0], 5), (keys[1], 30)):
            row = self.db.get(LoginThrottle, key)
            if row is None or aware(row.window_started_at) < moment - timedelta(minutes=15):
                if row is None:
                    row = LoginThrottle(throttle_key=key)
                    self.db.add(row)
                row.attempt_count = 1
                row.window_started_at = moment
                row.blocked_until = None
            else:
                row.attempt_count += 1
                if row.attempt_count >= limit:
                    minutes = min(15, 2 ** min(row.attempt_count - limit, 4))
                    row.blocked_until = moment + timedelta(minutes=minutes)
        self.db.commit()

    def authenticate(self, *, email: str, code: str, ip: str, user_agent: str) -> LoginResult | None:
        keys = self._throttle_keys(email, ip)
        if self._is_throttled(keys):
            AuditService(self.db).record(
                event_type="auth.login.throttled",
                outcome="FAILED",
                event_data={"account_reference": self._token_hmac(normalize_email(email))},
            )
            return None
        user = self.db.scalar(select(User).where(User.normalized_email == normalize_email(email), User.is_active.is_(True)))
        membership = None
        if user:
            membership = self.db.scalar(
                select(Membership).where(Membership.user_id == user.user_id, Membership.status == "active")
            )
        valid = False
        method = None
        if user and membership:
            valid, method = self._consume_user_code(user, code)
        if not valid or user is None or membership is None:
            self.db.rollback()
            AuditService(self.db).record(
                event_type="auth.login.failed",
                outcome="FAILED",
                organization_id=membership.organization_id if membership else None,
                actor_user_id=user.user_id if user else None,
                event_data={"account_reference": self._token_hmac(normalize_email(email))},
                commit=False,
            )
            self._record_failure(keys)
            return None
        self.db.execute(delete(LoginThrottle).where(LoginThrottle.throttle_key.in_(keys)))
        raw_session = secrets.token_urlsafe(32)
        moment = now_utc()
        session = AuthSession(
            user_id=user.user_id,
            membership_id=membership.membership_id,
            token_hmac=self._session_hmac(raw_session),
            csrf_token=secrets.token_urlsafe(24),
            created_at=moment,
            last_seen_at=moment,
            idle_expires_at=moment + timedelta(minutes=self.settings.session_lifetime_minutes),
            absolute_expires_at=moment + timedelta(hours=self.settings.session_absolute_lifetime_hours),
            ip_address=ip,
            user_agent=user_agent[:500],
        )
        self.db.add(session)
        AuditService(self.db).record(
            event_type="auth.login.succeeded",
            organization_id=membership.organization_id,
            actor_user_id=user.user_id,
            entity_type="session",
            entity_id=session.session_id,
            event_data={"method": method},
            commit=False,
        )
        self.db.commit()
        return LoginResult(raw_session, session, method == "recovery_code")

    def reauthenticate_administrator(
        self,
        *,
        user_id: str,
        code: str,
        ip: str,
        session_id: str | None = None,
    ) -> bool:
        """Require a fresh local credential before a privileged operation."""
        user = self.db.get(User, user_id)
        if user is None or not user.is_active:
            return False
        keys = self._throttle_keys(user.email, ip)
        if self._is_throttled(keys):
            AuditService(self.db).record(
                event_type="auth.admin.reauthentication_throttled",
                outcome="FAILED",
                actor_user_id=user_id,
                event_data={"account_reference": self._token_hmac(user.normalized_email)},
            )
            return False
        valid, method = self._consume_user_code(user, code)
        if not valid:
            self.db.rollback()
            AuditService(self.db).record(
                event_type="auth.admin.reauthentication_failed",
                outcome="FAILED",
                actor_user_id=user_id,
                event_data={"account_reference": self._token_hmac(user.normalized_email)},
                commit=False,
            )
            self._record_failure(keys)
            return False
        self.db.execute(delete(LoginThrottle).where(LoginThrottle.throttle_key.in_(keys)))
        session = self.db.get(AuthSession, session_id) if session_id else None
        if (
            session is not None
            and session.user_id == user_id
            and session.revoked_at is None
        ):
            session.reauthenticated_at = now_utc()
        AuditService(self.db).record(
            event_type="auth.admin.reauthenticated",
            actor_user_id=user_id,
            entity_type="session" if session is not None else "user",
            entity_id=session.session_id if session is not None else user_id,
            event_data={
                "method": method,
                "verification_window_minutes": self.settings.admin_reauthentication_minutes,
            },
            commit=False,
        )
        self.db.commit()
        return True

    def administrator_reauthentication_is_current(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        session = self.db.get(AuthSession, session_id)
        if session is None or session.revoked_at is not None or session.reauthenticated_at is None:
            return False
        return aware(session.reauthenticated_at) > now_utc() - timedelta(
            minutes=self.settings.admin_reauthentication_minutes
        )

    def _is_workspace_admin(self, membership: Membership) -> bool:
        return any(
            assignment.role.role_key == "workspace_admin"
            for assignment in membership.role_assignments
        ) or membership.role in {"admin", "workspace_admin"}

    def _active_admin_count(self, organization_id: str) -> int:
        memberships = self.db.scalars(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.status == "active",
            )
        ).all()
        return sum(
            1
            for membership in memberships
            if membership.user.is_active and self._is_workspace_admin(membership)
        )

    def _protect_last_admin(self, membership: Membership) -> None:
        if (
            membership.status == "active"
            and self._is_workspace_admin(membership)
            and self._active_admin_count(membership.organization_id) <= 1
        ):
            raise ValueError("The workspace must retain at least one active administrator")

    def revoke_membership_sessions(
        self,
        membership: Membership,
        *,
        actor_user_id: str,
        event_type: str = "auth.membership.sessions_revoked",
        commit: bool = True,
    ) -> int:
        moment = now_utc()
        result = self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.membership_id == membership.membership_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=moment)
        )
        count = int(result.rowcount or 0)
        AuditService(self.db).record(
            event_type=event_type,
            organization_id=membership.organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"subject_user_id": membership.user_id, "session_count": count},
            commit=False,
        )
        if commit:
            self.db.commit()
        return count

    def change_membership_role(
        self, membership: Membership, *, role_key: str, actor_user_id: str
    ) -> None:
        if membership.user_id == actor_user_id:
            raise ValueError("Another administrator must change your workspace role")
        current_roles = tuple(
            sorted(assignment.role.role_key for assignment in membership.role_assignments)
        )
        if current_roles == (role_key,):
            raise ValueError("The user already has that workspace role")
        if self._is_workspace_admin(membership) and role_key != "workspace_admin":
            self._protect_last_admin(membership)
        role = self.assign_role(
            membership, role_key, assigned_by_user_id=actor_user_id
        )
        self.revoke_membership_sessions(
            membership,
            actor_user_id=actor_user_id,
            event_type="auth.membership.sessions_revoked_for_role_change",
            commit=False,
        )
        AuditService(self.db).record(
            event_type="auth.membership.role_changed",
            organization_id=membership.organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"previous_roles": current_roles, "new_role": role.role_key},
            commit=False,
        )
        self.db.commit()

    def set_membership_status(
        self, membership: Membership, *, status: str, actor_user_id: str
    ) -> None:
        if status not in {"active", "suspended"}:
            raise ValueError("Unsupported membership status")
        previous = membership.status
        if status == "suspended":
            if membership.user_id == actor_user_id:
                raise ValueError("Another administrator must suspend your account")
            if previous != "active":
                raise ValueError("Only an active membership can be suspended")
            self._protect_last_admin(membership)
            membership.status = "suspended"
            membership.suspended_at = now_utc()
            self.revoke_membership_sessions(
                membership,
                actor_user_id=actor_user_id,
                event_type="auth.membership.sessions_revoked_for_suspension",
                commit=False,
            )
        else:
            if previous != "suspended":
                raise ValueError("Only a suspended membership can be reactivated")
            membership.status = "active"
            membership.suspended_at = None
            if membership.activated_at is None:
                membership.activated_at = now_utc()
        AuditService(self.db).record(
            event_type=(
                "auth.membership.suspended"
                if status == "suspended"
                else "auth.membership.reactivated"
            ),
            organization_id=membership.organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"previous_status": previous, "subject_user_id": membership.user_id},
            commit=False,
        )
        self.db.commit()

    def begin_reenrollment(
        self, membership: Membership, *, actor_user_id: str
    ) -> EnrollmentResult:
        if membership.user_id == actor_user_id:
            raise ValueError("Another administrator must reset your authenticator")
        self._protect_last_admin(membership)
        moment = now_utc()
        self.db.execute(
            update(Credential)
            .where(Credential.user_id == membership.user_id, Credential.revoked_at.is_(None))
            .values(revoked_at=moment)
        )
        self.db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == membership.user_id))
        membership.status = "pending"
        membership.suspended_at = None
        self.revoke_membership_sessions(
            membership,
            actor_user_id=actor_user_id,
            event_type="auth.membership.sessions_revoked_for_reenrollment",
            commit=False,
        )
        result = self.issue_enrollment(
            membership,
            created_by_user_id=actor_user_id,
            enforce_admission=False,
        )
        AuditService(self.db).record(
            event_type="auth.credential.reenrollment_started",
            organization_id=membership.organization_id,
            actor_user_id=actor_user_id,
            entity_type="membership",
            entity_id=membership.membership_id,
            event_data={"subject_user_id": membership.user_id},
            commit=False,
        )
        self.db.commit()
        return result

    def resolve_session(self, raw_token: str) -> AuthSession | None:
        session = self.db.scalar(
            select(AuthSession).where(
                AuthSession.token_hmac == self._session_hmac(raw_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        moment = now_utc()
        if session is None:
            return None
        if aware(session.idle_expires_at) <= moment or aware(session.absolute_expires_at) <= moment:
            session.revoked_at = moment
            self.db.commit()
            return None
        if not session.user.is_active or session.membership.status != "active" or not session.membership.organization.is_active:
            session.revoked_at = moment
            self.db.commit()
            return None
        session.last_seen_at = moment
        session.idle_expires_at = min(
            moment + timedelta(minutes=self.settings.session_lifetime_minutes),
            aware(session.absolute_expires_at),
        )
        self.db.commit()
        return session

    def revoke_session(self, session_id: str, actor_user_id: str | None = None) -> None:
        session = self.db.get(AuthSession, session_id)
        if session and session.revoked_at is None:
            session.revoked_at = now_utc()
            AuditService(self.db).record(
                event_type="auth.logout",
                organization_id=session.membership.organization_id,
                actor_user_id=actor_user_id or session.user_id,
                entity_type="session",
                entity_id=session_id,
                commit=False,
            )
            self.db.commit()
