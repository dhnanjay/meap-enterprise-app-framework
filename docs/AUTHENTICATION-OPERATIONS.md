# MEAP Local Authentication Operations

**Status:** Local authentication and professional account administration implemented
**Admission:** administrator-created, invite-only
**Identity assurance:** administrator asserted
**Credential:** TOTP or a single-use recovery code
**External services required:** none

MEAP's built-in authentication is intended for controlled deployments where an application administrator knows who should receive access. An email address is an account identifier and contact label; MEAP does not claim that the mailbox or employment status has been verified.

## 1. Security boundary

- There is no public registration or automatic domain admission.
- Only an administrator can create a membership and enrollment link.
- `MEAP_ALLOWED_EMAIL_DOMAINS` can restrict which domains administrators may enter; this is a restriction, not mailbox verification.
- Sensitive administrator actions require a fresh authenticator or recovery code on a dedicated confirmation screen.
- Suspending a membership and changing a role revoke active sessions immediately.
- The last active workspace administrator cannot be demoted, suspended, or reset for re-enrollment.
- Local TOTP credentials are stored separately from future OIDC identities.
- TOTP seeds use AES-GCM encryption with a versioned credential key.
- Enrollment and session tokens are stored as keyed HMAC values, never as bearer-token plaintext.
- A TOTP time-step counter is accepted once using an atomic database update.
- Server-side sessions have idle and absolute expiration.
- Unsafe authenticated requests require the per-session CSRF token.

TOTP is not phishing-resistant and does not provide automatic corporate offboarding. An administrator must suspend access when a user should no longer use MEAP.

## 2. Local bootstrap

Install dependencies and create or upgrade the database before bootstrap:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
meap db upgrade
python -m app.platform.auth.cli bootstrap-admin \
  --email admin@example.com \
  --display-name "MEAP Administrator" \
  --organization "Example Organization" \
  --base-url http://127.0.0.1:8000
```

The authentication CLI also checks and safely upgrades the database before accessing authentication tables. For SQLite, a required upgrade creates a timestamped backup. The command then writes the bootstrap marker to the database immediately and prints a one-time enrollment URL. It cannot create a second initial administrator.

The `--base-url` port must match the port used to start Uvicorn. For example, when Uvicorn uses `--port 8022`, pass `--base-url http://127.0.0.1:8022`.

If the first link expires before enrollment is completed, reissue it from the host:

```bash
python -m app.platform.auth.cli reissue-bootstrap-enrollment \
  --base-url http://127.0.0.1:8000
```

This works only while the database bootstrap is incomplete. It invalidates the previous unconsumed link.

## 3. User enrollment

1. Sign in as an administrator.
2. Open **Users** in the top bar.
3. Enter the email, display name, role, and your current administrator authentication code.
4. Confirm that you are asserting the user's identity and assigning access.
5. Copy the enrollment URL shown once and transfer it through a channel where you can identify the recipient.
6. The user scans the QR code and confirms a six-digit code.
7. The user saves the ten recovery codes shown once.

The administrator can then use **Application visibility and access** on the same page to enable or disable each registered application for that user. The setting changes both navigation visibility and direct route authorization. See [`ACCESS-CONTROL.md`](ACCESS-CONTROL.md).

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
MEAP_CSRF_KEY=<independent random value>
MEAP_TOKEN_HMAC_KEY=<independent random value>
```

`MEAP_CREDENTIAL_ENCRYPTION_KEY` remains a single-key local-development fallback. Production should use the JSON keyring so an old key can remain available for decryption while new credentials are written with the active key ID. Production startup refuses the committed local development keys. Store production values in the VM or deployment secret store, not in Git.

`MEAP_ADMISSION_MODE=disabled` means no new membership may be issued by bootstrap or administrator invitation. Existing memberships and sessions are unaffected, and an administrator may still reset the credential of an existing membership.

## 5. Database and migrations

Alembic is the schema authority for every runnable local, development, and production database:

```bash
meap db status
meap db upgrade
```

The application refuses to start against a stale schema and reports revision state through `/developer/health`. SQLite remains the zero-configuration default; PostgreSQL is selected through `MEAP_DATABASE_URL`. Read [`DATABASE-OPERATIONS.md`](DATABASE-OPERATIONS.md) before deployment.

## 6. Account administration and recovery

Open **Users**, then choose **Manage** for an account. The account page shows membership and credential status, active-session count, last sign-in, last activity, authenticator enrollment time, and unused recovery-code count.

The available operations are:

- Change the generic workspace role. Existing sessions are revoked so the new authorization is used immediately.
- Suspend an active membership. Sign-in is blocked and every session is revoked.
- Reactivate a suspended membership. The existing authenticator remains usable.
- Revoke all active sessions without changing the credential.
- Reset and re-enroll the authenticator. TOTP, recovery codes, and sessions are invalidated; a new 15-minute enrollment link is displayed once.
- Replace recovery codes. Existing codes are invalidated and ten replacements are displayed once.
- Enable or disable a registered application. The access matrix discovers entries from the navigation registry and the confirmation changes both link visibility and direct-route authorization.

Each operation has a review page, requires an explicit confirmation, requires the acting administrator's fresh TOTP or recovery code, and writes an audit event. A TOTP time step cannot be replayed: if the administrator used the current six-digit code to sign in, wait for it to change before confirming an operation.

MEAP prevents the last active workspace administrator from being demoted, suspended, or reset for re-enrollment. Create and enroll a second workspace administrator before performing one of those operations on the first.

### Lost device and offboarding

- A recovery code can be entered in the ordinary authentication-code field. Each code succeeds once.
- If recovery codes are exposed, replace them from the trusted application host. This immediately invalidates every previous recovery code:

```bash
python -m app.platform.auth.cli regenerate-recovery-codes \
  --email user@example.com
```

- If the device and recovery codes are both lost, an administrator uses **Reset and re-enroll authenticator**. The old seed is never revealed.
- To offboard a user, choose **Suspend account**.
- An administrator cannot suspend their own account from their current session. Another administrator must perform that operation.

## 7. Future OIDC integration

Business code receives a normalized `UserContext`; it does not inspect the authentication mechanism. A future `oidc` backend should populate the same user, organization, membership, role, and session fields and store stable `(issuer, subject)` pairs in `auth_external_identities`.

Do not share MEAP's credential tables directly with unrelated future applications. When multiple applications need common login, place Keycloak or another standards-compliant identity provider in front of them and configure each application as an independent OIDC client.

## 8. Operational FAQ

### How do I reset a local development installation?

The bootstrap marker, users, credentials, sessions, audit history, and business records live in the database. For the default local SQLite installation, the safest complete reset is to stop MEAP and move the database aside rather than delete it:

```bash
# 1. Stop uvicorn with Control-C.

# 2. Run these commands from the repository directory.
mv meap.db meap.before-reset.db

# 3. Create a new initial administrator enrollment.
source .venv/bin/activate
python -m app.platform.auth.cli bootstrap-admin \
  --email your-email@example.com \
  --display-name "Dhananjay" \
  --organization "Your Organization"

# 4. Start MEAP again.
uvicorn app.main:app --reload --port 8000
```

This creates a fresh `meap.db`. The old installation remains recoverable in `meap.before-reset.db`. If that backup filename already exists, choose a different filename rather than overwriting it.

Database reset does not remove `.venv`, source code, configuration, or files under `artifacts/`. If uploaded artifacts must also be reset, move that directory aside separately:

```bash
mv artifacts artifacts.before-reset
```

Do not use the SQLite reset procedure for PostgreSQL. Create a database backup and reset the intended PostgreSQL schema through the database administrator or deployment tooling. Never point a destructive reset at a database whose ownership is uncertain.

If only the initial enrollment link expired, do not reset anything. Use:

```bash
python -m app.platform.auth.cli reissue-bootstrap-enrollment \
  --base-url http://127.0.0.1:8000
```

This command works only while initial administrator enrollment is incomplete.

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
