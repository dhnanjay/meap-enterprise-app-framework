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

## 2026-08-13 — Generic access matrix and workspace data ownership

### Outcome

Added the first administrator-managed access layer for a generic, data-heavy application platform. Roles describe reusable operational capabilities rather than accounting job titles, and administrators can make per-user application exceptions from the UI.

### Added

- Generic role bundles: workspace administrator, operator, analyst, auditor, and viewer.
- Workspace-scoped role definitions, role permissions, membership roles, and explicit membership permission overrides.
- A Users-page access matrix listing every registered business-application navigation link for every workspace membership.
- Immediate per-user enable/disable changes with durable audit events.
- `required_permission` in the module navigation contract.
- Permission-filtered sidebar, dashboard, and application search results.
- Matching server-side view permission checks, including direct URL denial.
- Workspace administrator restriction for user administration and Developer diagnostics.
- `organization_id` ownership on reconciliation, exception, journal-review, and journal-entry records.
- Organization-scoped repositories for all reads, counts, lookups, and mutations.
- Actor/timestamp ownership fields for future interaction-level auditability.
- Alembic revision `3836580891fe`, including legacy data backfill and SQLite-safe batch operations.
- [`ACCESS-CONTROL.md`](ACCESS-CONTROL.md) as the developer and operator contract.

### Verification

- Full suite: 135 passed.
- Browser-flow test confirms an explicit deny removes the link and returns `403` for the direct route.
- Live local-browser verification covered the administrator matrix at desktop and narrow widths, the Enabled/Disabled transition, filtered workspace navigation, and direct-route denial.
- Contract tests cover permission-pattern expansion and permission-filtered navigation.
- Service tests confirm bank-reconciliation and journal-review identifiers cannot cross workspace boundaries.
- Fresh SQLite migration, autogenerate drift check, downgrade, re-upgrade, and second drift check succeeded on an isolated database.

### Current boundary

- The UI configures application-level view access first; action-level permissions remain role-driven and server-enforced.
- Dashboard remains the authenticated workspace home.
- Users and Developer are protected workspace-administration capabilities, not user-configurable business links.
- PostgreSQL migration validation remains the next database portability check.
- No code or repository state was published during this increment.

## 2026-08-13 — Access navigation synchronization correction

- Confirmed the current per-user allow records were correct; link navigation failed because the local `meap.db` still had the pre-workspace business schema.
- Added an explicit `get_configurable_navigation()` registry contract consumed by the Users access panel.
- Added regression coverage proving that removing a module removes its access-panel column and registering a new navigation link adds its column automatically.
- Added authenticated-page `Cache-Control: no-store` headers so browser history cannot resurrect navigation rendered before an access change.
- Kept the dashboard as fixed workspace chrome and Users/Developer as administrator-only platform capabilities.
- Backed up the existing local database as `meap.before-workspace-access-20260813.db`, stamped its previously empty Alembic baseline, and applied revision `3836580891fe`.
- Verified both users, all four per-user access overrides, and all four reconciliation records survived migration.
- Verified the live authenticated routes `/`, `/bank-recon`, `/je-review`, and `/auth/admin/users` all return HTTP 200 after migration.

## 2026-08-13 — Database lifecycle hardening

### Outcome

Made Alembic the single schema authority for every runnable MEAP environment, preventing an old database schema from surfacing later as non-working application links or SQL errors.

### Added

- `meap db status` for read-only revision inspection.
- `meap db upgrade` for migration to head.
- Automatic timestamped SQLite backup through SQLite's consistent backup API before schema changes.
- Explicit, backed-up downgrade command for controlled migration verification.
- Narrow legacy-schema fingerprinting for databases created by historical local `create_all()` startup.
- Fail-closed refusal to stamp unknown unversioned schemas.
- Startup revision enforcement for local, development, and production profiles.
- Automatic safe database preparation before authentication host commands.
- Database revision status in `/developer/health`.
- [`DATABASE-OPERATIONS.md`](DATABASE-OPERATIONS.md) with first-install, upgrade, recovery, downgrade, and PostgreSQL procedures.

### Verification scope

- Fresh SQLite installation to head.
- SQLite backup creation before downgrade and re-upgrade.
- Startup rejection while the database is behind head.
- Recognized unversioned legacy schema stamping, upgrade, and business-record preservation.
- Refusal of an unknown unversioned schema.
- Health response exposes current and expected revisions.
- Installed `meap db` entry point exercised through a fresh upgrade, backed-up downgrade, backed-up re-upgrade, and final current-status check on a disposable SQLite database.
- Full application test suite and Alembic drift check.

### Policy

- Test profile may use isolated metadata creation; runnable deployments may not.
- PostgreSQL backup remains an operator/deployment responsibility.
- No code or repository state was published during this increment.

## 2026-08-13 — Professional account administration

### Outcome

Extended the dynamic Users access matrix into a complete, self-hosted account-operations panel while preserving administrator-asserted identity and the zero-email, zero-IT authentication model.

### Added

- Per-account administration pages with membership status, generic role, active-session count, last sign-in, last activity, TOTP enrollment time, and remaining recovery-code count.
- Dedicated review and confirmation screens for role changes, suspension, reactivation, session revocation, authenticator reset/re-enrollment, recovery-code replacement, and application-access changes.
- Fresh administrator TOTP or recovery-code verification for every sensitive operation, using the existing replay protection and throttling controls.
- Immediate session revocation on role changes and suspension.
- Complete authenticator reset that invalidates the current TOTP credential, recovery codes, and sessions before issuing a one-time replacement enrollment link.
- One-time administrator-driven recovery-code replacement.
- Last-active-administrator protection for demotion, suspension, and authenticator reset.
- Success and failure audit events for privileged operations.
- Responsive account-summary and security-operation layouts.

### Verification

- Service coverage for one-time administrator reauthentication, last-administrator protection, role/session invalidation, suspend/reactivate, and complete re-enrollment invalidation.
- Browser-flow coverage for account status rendering, confirmation UI, administrator reauthentication, and one-time recovery-code replacement output.
- No database migration was needed; the increment uses the existing membership, role, credential, recovery-code, session, and audit schemas.

### Parked design direction

- Added [`LLM-MODULE-GENERATOR-ROADMAP.md`](LLM-MODULE-GENERATOR-ROADMAP.md).
- The future generator is optional and disabled by default. It will assemble architecture/design/schema context from source, generate only into an isolated workspace, run migrations and tests, show a reviewable diff, and require explicit human approval before export or merge.
- No LLM provider, runtime code generation, external upload, or production self-modification was added in this increment.

## 2026-08-13 — Application-access confirmation correction

- Reproduced `ERR-UNEXPECTED` when an administrator selected Enabled/Disabled in the Users access matrix.
- Corrected both confirmation-route lookups to consume the navigation registry's documented dictionary contract rather than treating entries as objects.
- Added end-to-end regression coverage for opening the access confirmation screen, reauthenticating the administrator, disabling the application, receiving a successful redirect, and receiving `403` on the disabled direct route.
- No database or persisted access records required repair; the failure occurred before the change was submitted.

## 2026-08-13 — Account-administration friction correction

- Reclassified registered-application visibility as a reversible, audited access-matrix change and restored its immediate one-click POST behavior with session CSRF validation.
- Added a configurable, server-side administrator verification window (`MEAP_ADMIN_REAUTHENTICATION_MINUTES`, default 10 minutes) for genuinely high-impact actions, replacing repeated authenticator prompts during one administration task.
- Persisted the verification timestamp on the opaque server-side session through Alembic revision `7f6a2a43d9c1`; no verification state is trusted from the browser.
- Removed self-defeating role, suspension, all-session revocation, and authenticator-reset controls from the current administrator's account page and added matching service/route rejection.
- Retained personal recovery-code replacement and renamed the status to **Unused backup sign-in codes**, with an explanation that each code works once.
- Replaced raw microsecond timestamps with concise UTC display values.
- Expanded tests for the verification window, immediate access toggle, direct-route denial, self-action protections, clarified UI, and code-free follow-up operations inside the window.

## 2026-08-13 — Developer diagnostics visibility hardening

- Added an explicit workspace-administrator role condition around both Developer entry points in the top bar and side navigation, in addition to the existing server-computed visibility flag.
- Confirmed `/developer` and `/developer/api/modules` fail closed with `403` for authenticated non-administrators.
- Added authenticated operator regression coverage proving the Developer link and icon are absent while workspace administrators retain visibility and access.
- Kept `/developer/health` unauthenticated as the narrow deployment-readiness probe; it exposes health/revision state, not the diagnostics interface or route/module inventory.

## 2026-08-13 — Separate administrator Audit Center

### Outcome

Added Audit as a dedicated, data-dense Platform panel rather than expanding the Users screen with an unrelated event history.

### Added

- Administrator-only `/audit` list report and `/audit/{event_id}` object page.
- Newest-first pagination with 25, 50, and 100-row options.
- Search across event type, correlation ID, entity identifier, actor name, and actor email.
- Exact event-type, outcome, actor, and inclusive date-range filters.
- Actor, entity, correlation, reproducibility, artifact, and structured event-data detail.
- Strict organization scoping in every audit list, count, filter facet, search, and detail query.
- Composite `(organization_id, occurred_at)` timeline index through Alembic revision `cc34e1a6f942`.
- [`AUDIT-CENTER.md`](AUDIT-CENTER.md) as the developer and operator contract.

### Security and UX boundaries

- Audit is visible only to workspace administrators and is enforced at the route as well as the navigation.
- A foreign-workspace event identifier returns not found.
- The panel is read-only and exposes no update or delete route.
- Export, retention controls, and cryptographic tamper evidence remain future increments.

### Verification

- Query coverage proves workspace isolation, actor resolution, search, and foreign-detail rejection.
- Authenticated browser-flow coverage proves administrator visibility, separate page rendering, filtering, detail rendering, and non-administrator `403` enforcement.
- Full suite: 157 passed.
- Alembic autogenerate check reports no schema drift.
- Local `meap.db` was backed up as `meap.before-upgrade-20260814-022015.db`, upgraded to `cc34e1a6f942`, and confirmed current.
- Browser-level layout inspection confirmed the filter bar wraps without document overflow, the side navigation becomes an overlay below 960px, and the dense table scrolls inside its own container at 800px and 600px viewports.
- No repository state was published during this increment.

## 2026-08-13 — Configurable roles and action permissions

### Outcome

Extended application-level user visibility controls with a separate, registry-driven Roles panel for reusable action-level authorization.

### Added

- Administrator-only workspace role list with effective permission and member counts.
- Deny-by-default custom-role creation with stable workspace-scoped role keys.
- Per-role action editor generated exclusively from active module permission declarations.
- Batched view, create, execute, resolve, escalate, flag, approve, reject, and future action grants.
- Dynamic custom-role availability in invitations and account role changes.
- Fixed `workspace_admin` safety role that cannot be reduced through the route or service.
- Exact registered-permission validation, foreign-workspace role rejection, affected-session revocation, and audit events.
- Clear precedence between role baselines and explicit per-user allow/deny overrides.
- [`ROLE-PERMISSIONS.md`](ROLE-PERMISSIONS.md) as the administrator and developer contract.

### UX and security decisions

- Roles remains separate from Users so the quick application matrix does not become an unreadable action grid.
- One batch save and the existing administrator verification window avoid repeated authenticator prompts.
- Built-in wildcard roles become exact reviewed grants after their first explicit save; custom roles are exact from creation.
- Custom-role deletion is deferred until safe reassignment and retention rules are implemented.

### Verification

- Service coverage exercises exact grants, workspace isolation, and administrator-role immutability.
- Authenticated browser-flow coverage creates and configures a custom role, assigns it to a user, confirms registered view access, and receives `403` for an ungranted create route.
- Session-invalidation coverage proves a role change revokes active sessions assigned to the role.
- Browser-level inspection confirmed the role list and action matrix have no document overflow at desktop or 600px; dense permission tables scroll only within their own containers.
- Full suite: 161 passed.
- Alembic autogenerate check reports no schema drift.
- No database migration is required; this increment activates the existing access-role schema.
- No repository state has been published.

## 2026-08-13 — Coding-agent engineering contract

### Outcome

Added a root-level [`AGENTS.md`](../AGENTS.md) as the normative, automatically discoverable operating contract for future LLM coding agents and automated development tools.

### Documented

- MEAP's priority order, state-location philosophy, Platform-to-module dependency direction, canonical module layers, and explicit registration model.
- Protected semantics for tenant ownership, identity/membership separation, credentials, server-side sessions, CSRF, permissions, administrator safety, append-only audit, jobs, artifacts, evidence, migrations, UI behavior, and the notebook boundary.
- A live schema map covering identity/access, Platform operations, and both example business modules, while distinguishing evolvable columns from sacrosanct meanings.
- Step-by-step protocols for adding a module, modifying an existing capability, and safely disabling or removing modules, pages, routes, fields, tables, and security-sensitive behavior.
- Data-heavy query, error/logging, UI/HTMX, future OIDC, and review-gated LLM module-generator rules.
- Change-risk verification requirements, prohibited shortcuts, definition of done, durable progress logging, and the difference between a local checkpoint and a published GitHub revision.
- The standing rule that no agent may upload, push, deploy, publish, create a remote, or open a pull request without explicit permission.

### Integration and verification

- Linked the agent contract from `README.md` and the developer customization guide so human and automated entry points converge on the same rules.
- Compared the schema map and contracts with the live SQLAlchemy models, module registry, composition root, settings, current migration policy, and existing normative documentation.
- Confirmed every local document referenced by the agent contract exists; full suite: 161 passed.
- This is a documentation-only increment; no runtime behavior or database schema changed.
- No repository state has been published.
