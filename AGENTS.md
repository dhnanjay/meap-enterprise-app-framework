# MEAP Coding-Agent Engineering Contract

**Status:** Normative  
**Audience:** LLM coding agents, autonomous development tools, and human maintainers  
**Scope:** The entire repository below this file

This is the first file a coding agent must read before modifying MEAP. It is the durable context needed to extend the application without eroding its architecture, security model, data ownership, or user experience.

This document is intentionally stricter than a general contributor guide. It tells an agent not only where code lives, but which meanings must survive every change and how to make narrowly scoped, reversible modifications.

## 1. Instruction precedence

Apply instructions in this order:

1. The user's current, explicit request.
2. Safety, privacy, and authorization constraints from the execution environment.
3. This `AGENTS.md` contract.
4. The focused normative documents linked from this file.
5. Existing code and tests.

If the request appears to require weakening a protected invariant, stop and explain the conflict before changing code. Do not silently reinterpret the request.

### Repository-specific user constraints

- **Never publish, upload, deploy, push, create a remote, or open a pull request without the user's explicit permission for that action.** A local commit is not permission to push it.
- Preserve unrelated user changes in a dirty worktree.
- Do not use destructive Git or filesystem commands to make the worktree convenient.
- Record every material development increment in `docs/DEVELOPMENT-PROGRESS.md`.
- Prefer a verified local Git checkpoint after a completed increment. State clearly whether the checkpoint is local or also present on a remote.

## 2. The mission

MEAP is a modular enterprise application platform for long-lived, data-heavy operational applications. Bank Reconciliation and Journal Entry Review are examples, not the boundaries of the product. New modules may support any controlled data workflow that benefits from durable state, traceability, permissions, review, and evidence.

The system is designed so that:

> An engineer or agent that understands one MEAP module should understand the structure, extension points, and debugging path of every MEAP module.

The architectural priority order is:

1. Predictability
2. Modularity
3. Maintainability
4. Debuggability
5. Traceability
6. Enterprise UI consistency
7. Developer productivity
8. Performance
9. Extensibility
10. Novelty

When two choices conflict, prefer the earlier quality. A clever abstraction that reduces predictability is a regression. A visually impressive interaction that weakens native forms or accessibility is a regression.

The state-location rule is:

> Business state lives in the database. Navigable view state lives in the URL. Ephemeral interaction state lives in the browser.

Do not put authoritative business state in browser storage, hidden client objects, or process memory.

## 3. Read the relevant contract before acting

Always read this file completely. Then read only the focused references relevant to the change:

| Change area | Required reference |
|---|---|
| General extension or a new module | `README.md`, `docs/DEVELOPER-CUSTOMIZATION-GUIDE.md` |
| Page structure, CSS, tables, status, copy | `docs/MEAP-DESIGN-LANGUAGE.md`, `docs/meap-styleguide.html` |
| User/application access | `docs/ACCESS-CONTROL.md` |
| Roles or action permissions | `docs/ROLE-PERMISSIONS.md` |
| Login, enrollment, sessions, credentials | `docs/AUTHENTICATION-OPERATIONS.md` |
| Models, migrations, upgrades, database recovery | `docs/DATABASE-OPERATIONS.md` |
| Audit events or Audit Center | `docs/AUDIT-CENTER.md` |
| Marimo or Jupyter integration | `docs/NOTEBOOK-SECURITY-MODEL.md` |
| LLM-assisted module creation | `docs/LLM-MODULE-GENERATOR-ROADMAP.md` |
| Current implementation history | `docs/DEVELOPMENT-PROGRESS.md` |

Documentation describes intent, but live models, migrations, tests, and registry contracts describe the current implementation. If they disagree, do not guess: identify the discrepancy and resolve it deliberately.

## 4. Architecture at a glance

```text
Browser
  native semantic HTML + MEAP CSS + Jinja + HTMX
      |
      v
FastAPI application
  middleware -> platform routes -> explicit module registry -> module routes
      |                                      |
      |                                      v
      |                         routes -> services -> repositories
      |                                      |
      v                                      v
Platform capabilities                  module-owned models
  auth, permissions, audit, jobs,           |
  artifacts, evidence, errors, DB            v
      |                                 SQLAlchemy / Alembic
      +--------------------+-----------------+
                           v
                  SQLite local/test
                  PostgreSQL deployment target
```

There are exactly two conceptual levels:

- **Platform:** cross-cutting capabilities needed by substantially every application.
- **Modules:** independently understandable business capabilities.

The dependency direction is sacred:

```text
business module -> platform
platform -X-> business module
```

`app/platform/` must never import a business module. The only application-composition point that imports module definitions is `app/main.py`.

## 5. Repository map and ownership

```text
app/
  main.py                         explicit composition root and MODULES list
  settings.py                     MEAP_* runtime configuration
  middleware/                     request-wide correlation/authentication
  platform/
    auth/                          identity, membership, credentials, sessions, access
    audit/                         append-only audit service and admin UI
    database/                      Base, engine/session, platform data models, migration checks
    diagnostics/                   administrator diagnostics and health probe
    errors/                        stable error taxonomy and handlers
    jobs/                          durable operation orchestration
    notebooks/                     notebook metadata policy boundary only
    registry/                      module, navigation, and permission contracts
    static/                        meap.css and locally served browser assets
    templates/                     shared shell, dashboard, platform pages, components
  modules/
    <module>/                      one business capability per directory
alembic/
  versions/                       the only deployment schema history
docs/                              normative guides and durable progress log
tests/                             unit, service, contract, migration, and browser-flow tests
```

When deciding where a change belongs, ask: “Would substantially every future MEAP application need this?” If yes, it may belong in Platform. If it expresses a business workflow or a domain-specific record, it belongs in a module. Do not move something into Platform merely so two current modules can share a shortcut; introduce a small generic platform contract only when the abstraction is stable and cross-cutting.

## 6. Canonical module structure

A complete business module follows this shape:

```text
app/modules/<module_name>/
  __init__.py
  module.py          identity, route, permissions, navigation, enablement
  permissions.py     stable permission constants
  models.py          persistence definitions only
  schemas.py         request/response and form validation
  repository.py      all database reads and writes
  service.py         business rules and orchestration
  routes.py          HTTP adaptation, auth checks, rendering/redirects
  jobs.py            optional long-running operation entry points
  templates/
    ...              module-owned Jinja pages and fragments
```

Keep these responsibilities separate:

### `module.py`

- Exports one immutable `MODULE: ModuleDefinition`.
- Declares identity and wiring only.
- Does not contain queries, business rules, or layout logic.
- A navigation entry declares `required_permission`; it is not inferred from a label.

### `permissions.py`

- Uses stable IDs in the form `<module>.<resource>.<action>`.
- Exposes constants used by routes and the module definition.
- Renaming a permission is a data migration and authorization compatibility decision, not a cosmetic refactor.

### `models.py`

- Contains SQLAlchemy persistence definitions and database-level constraints.
- Does not query, render, authorize, or implement workflows.
- New business-owned records normally require non-null `organization_id` and actor/time fields.

### `schemas.py`

- Validates and normalizes untrusted input.
- Keeps transport concerns out of ORM models and repositories.
- Defines explicit limits for search, pagination, strings, uploads, and enumerated values.

### `repository.py`

- Owns all SQL construction and persistence operations.
- Receives `organization_id` explicitly for tenant-owned data.
- Applies tenant scope in the SQL query itself, including single-ID lookups.
- Does not decide whether a user is allowed to perform a business action.

### `service.py`

- Owns business invariants, state transitions, and transaction-level orchestration.
- Calls repositories and platform capabilities such as jobs, artifacts, and audit.
- Does not depend on FastAPI request objects or render templates.
- Does not reimplement authentication, CSRF, or permission parsing.

### `routes.py`

- Converts HTTP input to typed service calls and service results to HTML/redirects.
- Enforces the exact server-side permission before invoking the service.
- Obtains the authenticated organization and actor from trusted request context.
- Uses the shared rendering boundary for full pages and HTMX fragments.
- Remains thin enough that business behavior can be tested without HTTP.

### `jobs.py`

- Delegates long work to the service layer.
- Persists durable job status and artifact references.
- Does not create a separate business architecture inside the worker.

## 7. The explicit registry is a protected design choice

`app/main.py` contains the explicit `MODULES` list. This is the single, deterministic answer to “which business modules exist in this application?”

Do not replace it with filesystem scanning, import side effects, decorators, entry-point magic, or a database-driven code loader. Explicit registration makes startup, testing, review, and removal predictable.

The registry consumes `ModuleDefinition` and `NavigationDefinition` from `app/platform/registry/definitions.py`. It drives:

- router mounting;
- permission registration;
- sidebar navigation;
- dashboard tiles;
- application search;
- the administrator Users access matrix;
- the Roles action matrix;
- diagnostics.

Therefore:

- Never hard-code a business-module list in shell, dashboard, Users, Roles, search, or diagnostics templates.
- Add or remove a module at the composition root and let registry consumers react.
- Add a new configurable link through a registered module definition, not by editing only the navigation HTML.
- Treat navigation visibility as presentation. The corresponding route must independently enforce its permission.

## 8. Protected invariants: what “sacrosanct” means

Sacrosanct does **not** mean no column can ever change. It means the semantics below cannot be removed, bypassed, or conflated without an explicit architecture decision, migration plan, security review, and user approval.

### 8.1 Identity and tenancy

- A `User` is a person-level identity; an `Organization` is a workspace; a `Membership` joins them.
- Do not put organization-specific role or status directly on `auth_users`.
- Business data is owned by an organization, not merely by a user or session.
- Every tenant-owned query is scoped by `organization_id` in SQL.
- Identifier lookup must use both record ID and organization ID. Never load globally and compare after retrieval.
- Foreign-organization records must look absent or forbidden according to the route contract; they must never leak data.
- Email is currently an administrator assertion, not mailbox verification or employment verification.

### 8.2 Authentication and credential material

- Local TOTP is the current self-hosted credential and requires no email or corporate tenant integration.
- TOTP secrets are encrypted at rest; token/session/recovery values are stored as keyed digests where applicable.
- Raw session tokens, enrollment tokens, TOTP seeds, encryption keys, and recovery codes must never be logged, audited, returned by APIs after their one allowed display, or committed.
- TOTP replay protection through the last accepted counter must remain atomic.
- Login rate limits and account/IP throttles cannot be bypassed by a new login route.
- The initial bootstrap marker is a database row. Never reopen bootstrap using an environment flag.
- External OIDC identities are keyed by immutable `(issuer, subject)`, not email. Email may be profile data, never the provider identity key.
- Adding Google or Microsoft login requires a real OIDC adapter and application registration. Do not pretend that a generic email address proves control of a corporate account.

### 8.3 Sessions and request integrity

- Sessions are opaque, server-side, revocable records.
- Cookies remain host-only where deployment permits, `HttpOnly`, `Secure` in production, and `SameSite=Lax` unless a separately reviewed model changes it.
- Rotate or revoke sessions when privilege or credential state changes.
- Every unsafe authenticated request validates the per-session CSRF token, including HTMX requests.
- Pre-authentication forms use signed, purpose-bound, expiring form tokens.
- The administrator verification window is stored server-side. Never trust a browser flag saying reauthentication occurred.
- Authentication and authorization fail closed.

### 8.4 Authorization

- Permissions have stable registry-backed IDs.
- The server route is the authorization boundary; hiding a link is not authorization.
- Effective access is derived from role grants and explicit membership overrides using the documented precedence.
- `workspace_admin` is the safety role and cannot be reduced through the configurable role editor.
- Prevent an administrator from performing self-defeating self-actions already prohibited by the service, and protect the last active administrator.
- Developer, Users, Roles, and Audit are administrator-only Platform surfaces, not ordinary configurable business links.
- Changes that affect active permissions revoke affected sessions so stale privilege cannot continue.

### 8.5 Audit

- `platform_audit_events` is append-only through application services.
- There is no edit or delete UI/API for an audit event.
- Auditable mutations record organization, actor, event type, outcome, entity, correlation ID, and safe context.
- `event_data` contains structured metadata, not secrets, credentials, raw uploaded data, or unbounded payloads.
- Audit reads are organization-scoped, including filters, facet lists, counts, search, and detail lookup.
- A failure worth investigating should preserve a correlation ID without exposing internal details to the user.

### 8.6 Jobs, artifacts, and evidence

These are separate concepts and must not be collapsed:

- A **Job** is a durable record of an operation and its lifecycle.
- An **Artifact** is a file or object with storage identity, checksum, provenance, and optional producing job.
- An **EvidenceItem** states why an artifact or locator supports a business entity.
- An **AuditEvent** records who did what and with what outcome.

A CSV is an artifact. “Rows 12–18 support exception X” is evidence. “User Y resolved exception X” is audit. “Import and classify this CSV” is a job.

### 8.7 Database lifecycle

- SQLAlchemy models describe the current schema; Alembic revisions are the only runnable-deployment schema history.
- `Base.metadata.create_all()` is allowed only for isolated tests.
- Never add startup `create_all()`, arbitrary Alembic stamping, or an automatic destructive reset.
- Never edit an applied migration to change history. Add a new revision.
- SQLite is the local/test default. PostgreSQL is the supported deployment target to preserve. Do not add SQLite-only production logic.
- SAP HANA is not a current supported database target. Do not introduce speculative dialect branches.

### 8.8 UI and interaction

- Native semantic elements own authoritative navigation and form input.
- HTMX enhances native behavior; it does not replace the HTTP contract.
- HTMX swaps ordinary light-DOM regions and does not target inside Shadow DOM.
- URL query parameters own filter, search, sort, pagination, and selected-view state that users may bookmark or navigate back to.
- Tables must remain useful at enterprise data volume. Do not turn queues into grids of decorative cards.
- The UI follows the Quiet Enterprise design language and its semantic status colors.
- Blue means interactive. Amber means attention or unexplained. Red is reserved for failure/destructive semantics. Green means cleared/success. Gray means neutral/not started.
- Money, dates, IDs, and dense figures use the documented numeric/identity typography.
- Print behavior is a supported accounting and workpaper use case, not an afterthought.

### 8.9 Notebook boundary

- `platform_notebooks` is currently a metadata and policy registry only.
- The application does not currently execute, spawn, proxy, or embed Jupyter or Marimo.
- A notebook installed in the same Python environment is still an independent code-execution surface.
- Never add an iframe or subprocess launcher as a “small” change. First implement the isolation, authorization, origin/proxy, filesystem, process ownership, token, network, audit, and lifecycle model in `docs/NOTEBOOK-SECURITY-MODEL.md`.

## 9. Current database schema map

This map is orientation, not a substitute for reading the live model and Alembic history. Before changing a table, inspect its model, relationships, indexes, every migration that touches it, and all repositories that query it.

### Identity and access tables

| Table | Meaning | Protected semantics |
|---|---|---|
| `auth_organizations` | Workspace/tenant | Stable organization ownership boundary |
| `auth_users` | Person-level asserted identity | Global identity remains separate from membership |
| `auth_memberships` | User membership in an organization | Unique organization/user association; lifecycle status |
| `auth_access_roles` | Workspace-scoped role definition | Stable role key per organization |
| `auth_role_permissions` | Role permission patterns/grants | Grants validated against live registry |
| `auth_membership_roles` | Membership-to-role assignment | Assignment is auditable and session-sensitive |
| `auth_membership_permissions` | Explicit allow/deny override | Exact permission, explicit effect, documented precedence |
| `auth_credentials` | Encrypted TOTP credential state | Encrypted secret, key version, replay counter, revocation |
| `auth_external_identities` | Reserved OIDC/provider identity | Unique immutable issuer/subject; not keyed by email |
| `auth_enrollment_tokens` | One-time enrollment ceremony | HMAC token, encrypted temporary seed, expiry, consumption |
| `auth_recovery_codes` | One-time backup sign-in codes | Keyed digest and single-use consumption |
| `auth_sessions` | Revocable server-side login session | Opaque HMAC token, CSRF, expiries, reauth, revocation |
| `auth_login_throttles` | Online-guessing protection | Durable account/IP throttling state |
| `auth_bootstrap_state` | Initial-admin lifecycle | Database-backed one-way bootstrap marker |

### Platform operation tables

| Table | Meaning | Protected semantics |
|---|---|---|
| `platform_jobs` | Durable operation lifecycle | Status, progress, errors, correlation, input/output artifacts |
| `platform_artifacts` | Stored file/object metadata | URI, checksum, type, provenance, source artifact, producing job |
| `platform_evidence` | Evidence-to-entity relationship | Semantic support and locator remain separate from file metadata |
| `platform_audit_events` | Append-only operational/security history | Organization and actor scope, outcome, correlation, safe metadata |
| `platform_notebooks` | Notebook registration metadata | Engine/mode/status/source/runtime/permission; no execution implied |

### Example business tables

| Table | Meaning | Extension pattern to preserve |
|---|---|---|
| `br_reconciliations` | Reconciliation header | Organization ownership, per-org reference, status, money, provenance, actor/time |
| `br_exceptions` | Reconciliation item requiring action | Organization ownership, parent FK, lifecycle, notes, actor/time |
| `je_reviews` | Journal-entry review header | Organization ownership, source artifact, status/counts, actor/time |
| `je_review_entries` | Review line item | Organization ownership, parent FK, amount/risk/status, actor/time |

The example business column names are not universal requirements. The patterns are: ownership, durable identifiers, database constraints, exact money types such as `Numeric(18, 2)`, explicit lifecycle state, provenance where applicable, and actor/timestamp attribution.

## 10. How to add a new module surgically

Follow this sequence. Do not begin by editing the sidebar or dashboard.

### Step 1: define the capability boundary

Write down:

- the business entity and lifecycle;
- list report, object page, and sub-object page needs;
- permissions by resource/action;
- organization ownership;
- inputs, outputs, artifacts, evidence, and audit events;
- whether work is synchronous or a durable job;
- expected row count, filtering, sorting, pagination, and export needs.

If this cannot be stated clearly, the module boundary is not ready.

### Step 2: declare stable permissions

Create `permissions.py` first. Use a module-specific namespace and concrete actions. Avoid role names inside permission IDs. A permission describes capability, not a job title.

Example:

```python
DATASET_VIEW = "dataset_operations.dataset.view"
DATASET_CREATE = "dataset_operations.dataset.create"
DATASET_EXECUTE = "dataset_operations.dataset.execute"
ITEM_RESOLVE = "dataset_operations.item.resolve"
```

### Step 3: model tenant-owned data

- Add `organization_id` to every tenant-owned header and child table.
- Add constraints and indexes based on actual query patterns.
- Use `Numeric`, never binary float, for money.
- Add source artifact/job references when lineage matters.
- Add created/updated actor and time fields for mutations.
- Create an Alembic revision and inspect it manually.

### Step 4: implement from storage outward

Implement in this order:

1. models and schemas;
2. organization-scoped repository;
3. business service;
4. audit/job/artifact integration;
5. thin permission-enforced routes;
6. templates and HTMX fragments;
7. module definition and registration;
8. tests and documentation.

This order makes invariants testable before presentation is added.

### Step 5: register exactly once

- Export `MODULE` from the module's `module.py`.
- Import it in `app/main.py`.
- Add it to `MODULES` in the intended display order.
- Do not also hand-add a dashboard tile, access-panel column, role action, or search entry.

If the module definition has navigation and a view permission, the registry should make those consumers update automatically. Add a contract test proving this behavior for any new registry capability.

### Step 6: verify the vertical slice

At minimum, prove:

- anonymous access redirects or fails according to the route class;
- an unauthorized user receives `403` from a direct URL;
- the authorized link and dashboard tile appear;
- per-user deny removes the link and blocks the direct URL;
- a foreign organization cannot list, count, search, retrieve, update, or infer the record;
- unsafe forms reject missing/invalid CSRF;
- list state survives URL reload and back/forward navigation;
- empty, loading, error, and realistic-volume table states render;
- the audit event contains safe actor/entity/correlation context;
- migration upgrade and drift checks pass.

## 11. How to modify an existing capability surgically

Before editing:

1. Check `git status --short` and preserve unrelated work.
2. Trace the complete call path: registry -> route -> service -> repository -> model/migration -> template -> tests.
3. Search for the permission, route name, model field, template block, and event type with `rg`.
4. Identify the invariant and the smallest seam that can express the change.
5. Add or update a regression test that fails for the observed behavior.

During editing:

- Change one layer only for that layer's responsibility.
- Prefer extending a typed contract over reaching across layers.
- Keep route and repository signatures explicit; avoid ambient globals.
- Do not combine an unrelated cleanup or architecture rewrite with a behavior fix.
- Do not rename stable IDs, routes, permissions, event types, or database columns only for aesthetic consistency.

After editing:

- Run the narrowest relevant test first, then the full suite.
- Run migration checks if model metadata was touched.
- Inspect the actual page at desktop and narrow widths for UI work.
- Update the relevant normative doc and `docs/DEVELOPMENT-PROGRESS.md`.
- Review the diff for secrets, local paths, generated databases, backup files, and scope creep.

## 12. How to remove a module, page, field, or behavior safely

Removal is a compatibility and retention operation, not just deletion.

### Removing or disabling a whole module

1. Create or identify a recoverable local checkpoint.
2. Determine whether the user wants temporary disablement or actual removal.
3. For temporary disablement, prefer `enabled=False` in the module definition.
4. For removal, delete its import and entry from `MODULES`.
5. Verify sidebar, dashboard, search, Users access matrix, Roles matrix, and diagnostics no longer list it.
6. Decide data retention separately. **Do not drop its tables by default.** Disabling code and destroying stored business records are different decisions.
7. If schema removal is explicitly approved, add a reversible migration where feasible and document backup/retention consequences.
8. Remove stale role grants or overrides only through a deliberate migration/service policy; do not silently rewrite access history.
9. Update tests, documentation, and progress log.

### Removing a route or page

- Search for named routes, navigation declarations, dashboard/search consumers, permissions, templates, tests, and documentation.
- Preserve a redirect only if backward compatibility is required and safe.
- Remove both discoverability and server behavior; never leave a link that cannot navigate.
- Do not remove the permission from the registry while a live route still relies on it.

### Removing a database field or table

- Identify retention, export, audit, and downgrade requirements first.
- Use Alembic; never modify a live database manually as part of application behavior.
- Use expand/migrate/contract phases when deployments may run mixed versions.
- Preserve audit meaning even when the source entity is retired.
- Test upgrade from the previous head, downgrade if supported, re-upgrade, and `alembic check`.

### Removing a security control

Do not do this as routine refactoring. Authentication, tenant scoping, CSRF, session revocation, throttling, secret protection, administrator safety, and audit append-only behavior require an explicit security decision and replacement control.

## 13. Database change protocol

Run database commands from the repository root so relative SQLite URLs resolve consistently.

### Before a schema change

- Read `docs/DATABASE-OPERATIONS.md`.
- Inspect the current revision with `.venv/bin/meap db status`.
- Read the current model and recent revisions affecting it.
- Decide how existing rows receive any new non-null value.
- Account for both SQLite and PostgreSQL behavior.

### Implementing a schema change

1. Modify the SQLAlchemy model.
2. Generate a new Alembic revision.
3. Read every generated operation; autogenerate is not design authority.
4. Give constraints and indexes stable names.
5. Use batch-safe operations where SQLite requires them.
6. Make data backfills explicit and deterministic.
7. Avoid dialect-specific types or SQL unless guarded by a tested portability strategy.

### Verification

At minimum:

```bash
.venv/bin/python -m pytest -q
.venv/bin/alembic check
.venv/bin/meap db status
```

For a migration, additionally test on a disposable database:

- fresh upgrade to head;
- upgrade from the prior head with representative legacy rows;
- downgrade when the revision claims to support it;
- re-upgrade;
- schema drift check;
- preservation of tenant IDs, access records, and business data.

Use `.venv/bin/meap db upgrade` for the configured local database because it creates a consistent SQLite backup before migration. Do not delete `meap.db` merely to make a migration pass.

## 14. Authentication and authorization extension rules

### Current login model

The current default is invite-only, administrator-asserted email plus TOTP. It is deliberately self-hosted and works on a laptop or VM without SMTP, mailbox access, Google Workspace administration, or Microsoft Entra tenant cooperation.

This verifies possession of the enrolled authenticator, not ownership of the email mailbox or current employment.

### Future OIDC providers

Google or Microsoft login belongs behind an authentication-provider adapter. A correct implementation must:

- be optional and configuration-controlled;
- use Authorization Code flow with PKCE, state, and nonce;
- validate issuer, audience, signature, time claims, and redirect URI;
- key identity on issuer/subject;
- apply the existing admission/membership policy after authentication;
- create the same server-side MEAP session rather than placing provider tokens in the browser session;
- store refresh/access tokens only if a separately approved downstream API use requires them;
- preserve local TOTP as an independent provider where configured.

Do not couple Gmail/Outlook mailbox APIs to login. Authentication and mailbox access are different permission surfaces.

### Adding a protected operation

- Define a registry permission.
- Enforce it at the route.
- Pass trusted actor and organization into the service.
- Determine whether the operation needs administrator reauthentication and session revocation.
- Emit success and meaningful failure audit events.
- Test direct-route denial, not just hidden navigation.

## 15. UI/UX extension rules

The intended design language is Quiet Enterprise: restrained surfaces, high information density, predictable archetypes, and sparse semantic color.

### Page archetypes

Use the same hierarchy across modules:

1. **Dashboard/launchpad:** discovery of registered workspaces.
2. **List report:** searchable, filterable, sortable, paginated work queue.
3. **Object page:** one entity's identity, status, key values, work areas, and actions.
4. **Sub-object page:** focused detail for an exception, item, entry, evidence record, or operation.

### Non-negotiable presentation rules

- Use tokens and existing `meap-` components before adding CSS.
- Do not use shadow + border + large radius + large padding as redundant separators.
- Keep object headers compact; do not spend the first screen on oversized KPI cards.
- Use tabular figures for money, dates, counts, and dense identifiers as specified.
- Reserve monospace for machine identity such as record IDs, correlation IDs, reason codes, and checksums—not ordinary money or dates.
- Dense tables scroll inside their container at narrow widths; the entire document must not gain horizontal overflow.
- Sidebar collapse must allow the main content to take available width; no fixed-width clipping.
- Native `href`, `action`, `method`, and named inputs remain valid without JavaScript.
- Maintain keyboard focus, labels, error association, and sensible reading order.
- Render clear empty and error states without pretending zero records is a successful business outcome.
- Preserve print styles for review and workpaper pages.

### HTMX contract

- GET requests perform navigation, search, filter, sort, and pagination.
- Unsafe methods perform mutations and require CSRF.
- Full requests render the page shell; HTMX requests render the targeted fragment through the shared rendering boundary.
- Prefer server-returned HTML over a parallel JSON/client-state application.
- Do not introduce a second front-end framework for an ordinary module.

## 16. Data-heavy operation rules

Design with thousands of rows, not demo-sized datasets.

- Paginate at the database, never after loading all rows.
- Push filtering, sorting, aggregation, and tenant scope into SQL.
- Whitelist sortable fields; never interpolate user input into SQL identifiers.
- Bound page size and search length.
- Add indexes based on query patterns and verify their portability.
- Avoid N+1 queries in list reports and permission/audit facets.
- Make bulk operations explicit jobs when their duration or failure mode exceeds an HTTP request.
- Preserve partial-failure evidence and a correlation ID for long operations.
- Treat uploaded files as untrusted artifacts and retain provenance/checksum metadata.
- Avoid showing false precision or binary floating-point money.

## 17. Error, logging, and audit behavior

- Raise typed MEAP errors for expected domain, validation, permission, and infrastructure conditions.
- The user receives a safe message and correlation ID; logs retain diagnostic context.
- Never return raw exceptions, SQL, filesystem paths, configuration values, or stack traces to end users.
- Use structured logs with stable event names.
- Do not log full business datasets, authentication codes, cookies, tokens, or encryption material.
- An audit event is not a debug log. Audit describes durable accountability; logs support operation and diagnosis.

## 18. LLM-agent and module-generator safety

An agent working in this repository may assist development, but the running application must not silently rewrite itself.

Any future in-app LLM module generator must remain:

- optional and disabled by default;
- provider-independent at the platform boundary;
- supplied with an explicit, versioned architecture/design/schema context bundle;
- isolated from production source, credentials, and databases;
- limited to a staging/worktree output area;
- review-gated with a complete diff;
- subject to formatting, static checks, tests, migration checks, and security checks;
- unable to merge, deploy, push, or execute destructive migrations without explicit human authorization;
- prohibited from uploading source code, schemas, business data, secrets, or artifacts unless the operator knowingly configures and approves that provider/data path.

Generated output must follow the same canonical module structure. The generator is not permission to create an alternate architecture, generic “god service,” dynamic code loader, or production self-modification endpoint.

## 19. Change-risk classification and verification matrix

Use the highest applicable class.

| Change | Minimum verification |
|---|---|
| Documentation only | Link/path check, factual comparison to live code, diff review |
| Template/CSS only | Focused tests, desktop and narrow browser inspection, no-overflow check |
| Route or permission | Focused route tests, anonymous/unauthorized/authorized paths, direct URL denial, CSRF where unsafe |
| Repository/query | Service tests, tenant-isolation tests, pagination/filter/sort correctness |
| Service mutation | State-transition tests, authorization, audit success/failure, concurrency/rollback reasoning |
| Auth/session/credential | Security-focused tests plus full browser flow; replay, throttle, revocation, CSRF, secret review |
| Model/migration | Fresh/legacy upgrade, drift check, preservation checks, downgrade/re-upgrade as supported |
| Registry/platform contract | Contract tests across current and synthetic modules plus full suite |
| Notebook execution boundary | Separate threat model and explicit approval before implementation |

Always finish with the full test suite unless the environment makes it impossible. If verification is incomplete, say exactly what was not run and why.

## 20. Prohibited shortcuts and common failure modes

Do not:

- hard-code module names in Users, Roles, dashboard, shell, search, or diagnostics;
- use navigation visibility as the only authorization check;
- query tenant-owned data without `organization_id` in the SQL predicate;
- put business rules in route functions or templates;
- query the database directly from templates;
- use raw SQL built from user strings;
- add `create_all()` to runnable startup;
- stamp or delete a database to hide migration drift;
- edit a historical migration already in use;
- store money in `float`;
- store plaintext credentials, session tokens, recovery codes, or enrollment tokens;
- log secrets or copy them into audit `event_data`;
- accept OIDC identity by email alone;
- add email sending as an implicit requirement of local login;
- add mailbox scopes to implement authentication;
- embed Jupyter/Marimo without the notebook security boundary;
- introduce React/Vue or a component framework for an ordinary form/table page;
- replace native form state with fragile client-only state;
- make a broad refactor while fixing a narrow defect;
- delete business data because a module is being hidden;
- create a GitHub repository, push, publish, upload, deploy, or open a PR without explicit permission.

## 21. Surgical work protocol for an agent

Use this sequence for every material task.

### A. Orient

1. Read this file and the relevant focused contracts.
2. Inspect `git status --short`, current branch, and recent commits.
3. Locate the live composition, model, migration, permission, route, service, repository, template, and tests.
4. State the intended invariant and the bounded change.

### B. Establish a baseline

1. Run the focused existing tests if practical.
2. For database work, inspect revision status before mutation.
3. For a reported UI defect, reproduce it at the actual viewport and interaction path.
4. Do not assume a screenshot proves the backend cause.

### C. Change the smallest coherent slice

1. Patch the owning layer.
2. Add a regression test or contract test.
3. Extend outward only when a typed contract requires it.
4. Preserve existing names and behavior outside scope.

### D. Verify proportionally

1. Focused tests first.
2. Full suite.
3. Alembic drift/migration checks when applicable.
4. Browser inspection for actual UI behavior.
5. Diff and secret review.

### E. Leave a durable handoff

Update `docs/DEVELOPMENT-PROGRESS.md` with:

- date and increment name;
- outcome in plain language;
- files/contracts/schema affected;
- security and architecture decisions;
- verification performed and result;
- known limitations or next recommended increment;
- whether anything was published (normally: no).

Then create a local commit/checkpoint if requested or consistent with the current workflow. Never describe a local commit as a GitHub checkpoint unless it was actually pushed with explicit permission.

## 22. Definition of done

A change is complete only when all applicable statements are true:

- The behavior meets the user's request without broadening scope.
- Platform does not import a business module.
- Registry-driven consumers remain synchronized.
- Direct routes enforce permissions independent of navigation.
- Tenant-owned SQL is scoped by organization.
- Unsafe requests validate CSRF.
- Sensitive operations preserve session and administrator safety rules.
- Mutations emit safe, organization-scoped audit evidence.
- Database changes have a reviewed migration and no drift.
- UI follows the MEAP archetype, density, semantic color, responsive, and native-HTML rules.
- Focused and full tests pass, or the exact gap is reported.
- Relevant documentation and the progress log are updated.
- The diff contains no secret, generated database, local backup, machine-specific path, or unrelated rewrite.
- No upload, push, deployment, or publication occurred without explicit permission.

## 23. Quick decision guide

**“I need a new business page.”**  
Add it inside the owning module. If it represents a new independent capability, create a canonical module and register it once.

**“I need a new sidebar link and dashboard tile.”**  
Declare registered module navigation with a required permission. Do not edit each consumer.

**“I need to hide a feature from one user.”**  
Use the existing membership permission override through the access service/UI; also enforce the route permission.

**“I need action-level access for a reusable group.”**  
Use a workspace role and registry-declared permissions, not a new hard-coded job-title enum.

**“I need to store a file.”**  
Create an Artifact. Link it to a Job and source Artifact where relevant. Add Evidence when it supports a business assertion.

**“I need a long calculation.”**  
Create a durable Job and persist progress/output artifacts. Do not hold the HTTP request indefinitely.

**“I need a schema change.”**  
Change the model, create a new Alembic revision, migrate existing data deliberately, and test both SQLite and PostgreSQL-compatible behavior.

**“I want to remove a module.”**  
Unregister it first and decide data retention independently. Do not drop tables merely because the UI is gone.

**“I want Jupyter or Marimo in the app.”**  
Stop and apply the notebook security model. Same machine or same virtual environment does not make notebook execution safe to embed.

**“I want Google or Microsoft login.”**  
Implement an optional OIDC provider adapter and retain issuer/subject identity. Do not confuse login with Gmail/Outlook mailbox access.

**“I want an LLM to build modules.”**  
Use the review-gated isolated generator plan. Generated code remains ordinary MEAP code and must pass every contract in this file.

## 24. Final principle

MEAP is extended by adding a small, explicit vertical slice through known seams. It is not extended by bypassing those seams.

When uncertain, choose the change that leaves the next agent with fewer hidden dependencies, a clearer registry, a narrower diff, stronger tenant isolation, and better evidence of what happened.
