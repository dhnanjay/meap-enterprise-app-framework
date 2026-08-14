# MEAP Development Progress

This file is the durable handoff log for material development increments. Update it whenever code, schema, security posture, deployment behavior, or developer-facing configuration changes.

## 2026-08-13 — Local invite-only TOTP authentication

### Outcome

Implemented the first complete self-hosted authentication path. It needs no SMTP, Google, Microsoft, Azure, WorkOS, or corporate IT integration.

### Added

- Administrator-asserted users, organizations, memberships, credentials, recovery codes, external-identity reservation, enrollment tokens, sessions, throttles, and a database bootstrap marker.
- One-time CLI bootstrap and incomplete-bootstrap enrollment reissue.
- Server-generated TOTP QR enrollment and first-code confirmation.
- AES-GCM encryption for TOTP seeds with an independent versioned key.
- HMAC storage for enrollment, session, and high-entropy recovery tokens.
- Atomic TOTP replay prevention with a ±1 time-step validation window.
- Layered database-backed account/IP and IP throttling.
- Ten single-use recovery codes.
- Opaque server-side sessions with idle and absolute expiration.
- Fail-closed request authentication and authenticated-request CSRF validation.
- Login, enrollment, recovery-code display, logout, user administration, invitation, and suspension UI.
- Immediate session revocation when a membership is suspended.
- Production refusal of committed local-development authentication keys.
- Alembic revision `4bd8a81af4b4`.
- Security-focused service and full browser-flow tests.

### Explicit policy decisions

- Email is `admin_asserted`; it is not marked verified.
- Domain allowlists restrict administrator input but do not enable self-registration.
- Local TOTP is a credential, not an external identity provider.
- OIDC identities remain a separate future adapter.
- No email is sent by the application.
- No code or repository state was published during this increment.

### Verification

- Authentication-focused tests: 7 passed after key-rotation coverage.
- Full suite: 126 passed after the final hardening pass.
- Alembic autogenerate drift check: no pending operations.
- Authentication migration: downgrade to the prior revision and re-upgrade both succeeded on an isolated SQLite database.
- Browser-level integration covers enrollment, login, authenticated workspace access, CSRF-protected logout, replay rejection, recovery-code single use, and anonymous redirect.

### Deferred

- Administrator-driven TOTP re-enrollment after a user loses both device and recovery codes.
- Reactivation and role-change UI with step-up authentication.
- Multiple simultaneous organization memberships at login selection time.
- OIDC/Keycloak/Google/Microsoft adapters.
- Passkeys/WebAuthn.
- Email notifications.

### Next recommended increment

Add administrator-controlled credential re-enrollment and an access-review page, including forced session revocation, administrator reauthentication, audit events, and tests. Then test the same schema and migration against PostgreSQL.

## 2026-08-13 — Local reset operations documentation

- Documented a recoverable SQLite factory-reset procedure that moves `meap.db` aside before creating a new installation.
- Clarified that database reset invalidates all users, credentials, sessions, audit history, and business records, while source code, `.venv`, configuration, and artifact files remain separate.
- Documented optional artifact-directory preservation and the non-destructive expired-bootstrap enrollment reissue command.
- Explicitly excluded PostgreSQL from the file-based SQLite reset procedure.

## 2026-08-13 — Authentication multi-tab CSRF correction

### Problem reproduced

Opening or refreshing the login page after opening an enrollment page replaced a shared pre-authentication CSRF cookie. Submitting the still-valid enrollment form then incorrectly reported that the form had expired.

### Correction

- Separated login and enrollment CSRF cookies.
- Scoped the login cookie to `/auth/login`.
- Scoped each enrollment cookie to its exact one-time enrollment URL.
- Added browser-flow coverage that opens login between enrollment-page load and enrollment confirmation.
- Kept the enrollment token, TOTP secret, and session security model unchanged.

## 2026-08-13 — Stateless pre-authentication CSRF tokens

### Live-browser finding

Enrollment completed, but a real browser still rejected the subsequent login form because the pre-authentication cookie was unavailable or replaced. The database confirmed that the administrator membership and bootstrap were active; the failure was isolated to login-form CSRF state.

### Correction

- Replaced pre-authentication CSRF cookies with signed, purpose-bound, 15-minute form tokens.
- Bound login tokens to `login` and enrollment tokens to the exact enrollment database record.
- Added a separate `MEAP_CSRF_KEY`; production refuses its committed local default.
- Preserved per-session CSRF validation for authenticated unsafe requests.
- Removed browser cookie ordering, tab replacement, hostname, and cookie-path behavior from enrollment and login form validity.

### Recovery-code exposure response

- Added the host-only `regenerate-recovery-codes --email` operation.
- Rotation deletes all prior recovery-code records, generates ten new 128-bit single-use codes, and records an audit event.
- This permits immediate recovery after codes are accidentally included in a screenshot without resetting the user or TOTP credential.
