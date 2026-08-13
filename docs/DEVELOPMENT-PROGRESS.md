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
