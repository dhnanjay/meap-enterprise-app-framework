# MEAP Local Authentication Operations

**Status:** Release 1 implemented  
**Admission:** administrator-created, invite-only  
**Identity assurance:** administrator asserted  
**Credential:** TOTP or a single-use recovery code  
**External services required:** none

MEAP's built-in authentication is intended for controlled deployments where an application administrator knows who should receive access. An email address is an account identifier and contact label; MEAP does not claim that the mailbox or employment status has been verified.

## 1. Security boundary

- There is no public registration or automatic domain admission.
- Only an administrator can create a membership and enrollment link.
- `MEAP_ALLOWED_EMAIL_DOMAINS` can restrict which domains administrators may enter; this is a restriction, not mailbox verification.
- Suspending a membership revokes its active sessions immediately.
- Local TOTP credentials are stored separately from future OIDC identities.
- TOTP seeds use AES-GCM encryption with a versioned credential key.
- Enrollment and session tokens are stored as keyed HMAC values, never as bearer-token plaintext.
- A TOTP time-step counter is accepted once using an atomic database update.
- Server-side sessions have idle and absolute expiration.
- Unsafe authenticated requests require the per-session CSRF token.

TOTP is not phishing-resistant and does not provide automatic corporate offboarding. An administrator must suspend access when a user should no longer use MEAP.

## 2. Local bootstrap

Install dependencies and start with a migrated or local auto-created database:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -m app.platform.auth.cli bootstrap-admin \
  --email admin@example.com \
  --display-name "MEAP Administrator" \
  --organization "Example Organization" \
  --base-url http://127.0.0.1:8000
```

The command writes the bootstrap marker to the database immediately and prints a one-time enrollment URL. It cannot create a second initial administrator.

If the first link expires before enrollment is completed, reissue it from the host:

```bash
python -m app.platform.auth.cli reissue-bootstrap-enrollment \
  --base-url http://127.0.0.1:8000
```

This works only while the database bootstrap is incomplete. It invalidates the previous unconsumed link.

## 3. User enrollment

1. Sign in as an administrator.
2. Open **Users** in the top bar.
3. Enter the email, display name, and role.
4. Copy the enrollment URL shown once and transfer it through a channel where you can identify the recipient.
5. The user scans the QR code and confirms a six-digit code.
6. The user saves the ten recovery codes shown once.

No email is sent. The administrator is responsible for confirming the recipient before sharing the enrollment URL.

## 4. Configuration

```dotenv
MEAP_AUTH_ENABLED=true
MEAP_AUTH_METHOD=local_totp
MEAP_ADMISSION_MODE=invite_only
MEAP_ALLOWED_EMAIL_DOMAINS=example.com,subsidiary.example
MEAP_SESSION_LIFETIME_MINUTES=480
MEAP_SESSION_ABSOLUTE_LIFETIME_HOURS=24
MEAP_ENROLLMENT_LIFETIME_MINUTES=15
```

Generate independent production keys; do not reuse a session key as a credential-encryption key:

```bash
python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Assign the outputs separately:

```dotenv
MEAP_CREDENTIAL_ENCRYPTION_KEYS='{"prod-v1":"<base64 32-byte key>"}'
MEAP_CREDENTIAL_ENCRYPTION_KEY_ID=prod-v1
MEAP_SESSION_HMAC_KEY=<independent random value>
MEAP_TOKEN_HMAC_KEY=<independent random value>
```

`MEAP_CREDENTIAL_ENCRYPTION_KEY` remains a single-key local-development fallback. Production should use the JSON keyring so an old key can remain available for decryption while new credentials are written with the active key ID. Production startup refuses the committed local development keys. Store production values in the VM or deployment secret store, not in Git.

`MEAP_ADMISSION_MODE=disabled` means no new enrollment may be issued by bootstrap or administrator invitation. Existing memberships and sessions are unaffected.

## 5. Database and migrations

Local, development, and test profiles create missing tables automatically. Production uses Alembic:

```bash
alembic upgrade head
```

The authentication schema is database-neutral SQLAlchemy and has an Alembic migration. SQLite remains the zero-configuration default; PostgreSQL is selected through `MEAP_DATABASE_URL`. OIDC identities have their own reserved table so a future identity provider does not require business-table redesign.

## 6. Lost device and offboarding

- A recovery code can be entered in the ordinary authentication-code field. Each code succeeds once.
- If the device and recovery codes are both lost, an administrator must issue a new enrollment in a future recovery-management increment. Never reveal the old seed.
- To offboard a user now, choose **Suspend**. This changes the membership state and revokes its active sessions.
- Administrators cannot suspend their own active membership through the UI.

## 7. Future OIDC integration

Business code receives a normalized `UserContext`; it does not inspect the authentication mechanism. A future `oidc` backend should populate the same user, organization, membership, role, and session fields and store stable `(issuer, subject)` pairs in `auth_external_identities`.

Do not share MEAP's credential tables directly with unrelated future applications. When multiple applications need common login, place Keycloak or another standards-compliant identity provider in front of them and configure each application as an independent OIDC client.

## 8. Operational FAQ

### Does the email address have to receive mail?

No. It is an administrator-asserted identifier. MEAP sends no email in this release.

### Does an allowed domain prove employment?

No. It only prevents administrators from entering addresses outside the configured list.

### Can users enroll themselves because they know the company domain?

No. Enrollment remains administrator-issued.

### Can the same six-digit code be replayed?

No. MEAP records and atomically advances the last accepted TOTP counter.

### Is this corporate SSO?

No. It is self-contained local authentication. OIDC is the future SSO boundary.

### Are notebooks exempt from authentication?

No. Notebook registry and future same-environment proxy routes remain behind the same session, permission, CSRF, origin, and audit boundaries described in `NOTEBOOK-SECURITY-MODEL.md`.
