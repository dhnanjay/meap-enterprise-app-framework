# MEAP Developer Customization Guide

**Status:** Maintainer guide
**Audience:** Engineers extending or deploying MEAP
**Scope:** Navigation, authentication, new pages, backend logic, persistence, migrations, testing, and common failures

This guide describes the code that exists in this repository and the supported path for extending it. Read the [MEAP Design Language](MEAP-DESIGN-LANGUAGE.md) before building a new screen, and use the [live style guide](meap-styleguide.html) while implementing templates.

## 1. Configuration model

Application settings live in `app/settings.py`. `pydantic-settings` loads values in this order:

1. Code defaults
2. Values in `.env`
3. Process environment variables

All environment variables use the `MEAP_` prefix. For example:

```dotenv
MEAP_PROFILE=development
MEAP_APP_NAME="Finance Operations"
MEAP_DATABASE_URL=postgresql+psycopg://meap:password@localhost/meap
MEAP_DEVELOPER_AREA_ENABLED=true
MEAP_AUTH_ENABLED=false
```

Do not commit `.env`, client secrets, database passwords, signing keys, access tokens, or refresh tokens. Production secrets should come from the deployment platform's secret manager. The default `MEAP_SECRET_KEY` is for local development only.

`get_settings()` is cached. Tests that change environment variables must call `get_settings.cache_clear()` before creating the app and again during cleanup.

## 2. Configure the navigation bar

Navigation is assembled from registered modules. A business module contributes metadata; it does not edit the global sidebar.

### Change a module's navigation entry

Edit the module's `module.py`:

```python
MODULE = ModuleDefinition(
    id="bank_reconciliation",
    name="Bank Reconciliation",
    route_prefix="/bank-recon",
    router=router,
    permissions=ALL_PERMISSIONS,
    navigation=NavigationDefinition(
        label="Bank Reconciliation",  # visible link text
        group="Accounting",           # sidebar section
        order=20,                      # order within the section
        icon="compare-arrows",        # reserved metadata; not rendered in v1
    ),
    description="...",
    enabled=True,
)
```

The registry sorts groups alphabetically, then sorts items by `order` and `label`. Use gaps such as 10, 20, and 30 so a later item can be inserted without renumbering everything.

### Add, remove, hide, or disable an entry

- **Add a module:** import its `MODULE` and add it to the explicit `MODULES` list in `app/main.py`.
- **Remove an application capability:** remove it from `MODULES`.
- **Temporarily disable a capability:** set `enabled=False` in its `module.py`. Its routes, permissions, and navigation will not be registered.
- **Keep routes but omit navigation:** set `navigation=None`. This is appropriate for callback or supporting modules, not as a security control.
- **Hide the Developer area:** set `MEAP_DEVELOPER_AREA_ENABLED=false`.

Do not hard-code business links in `app/platform/shell/templates/shell_page.html`. That template owns platform chrome only: product identity, search, density, profile/status controls, responsive navigation, and the page content region.

The `icon` field is intentionally not rendered in the current Quiet Enterprise navigation. Adding an icon library is a platform design decision, not a per-module customization.

### Navigation verification checklist

After a change, verify:

- The label and group are correct at desktop and narrow widths.
- Sidebar collapse expands the content region without clipping or horizontal page overflow.
- The route works by direct URL, not only by clicking the link.
- A disabled module produces a 404 for its routes.
- Permissions are still enforced on the server. Hiding a link never grants or removes access.

## 3. Authentication: current state and production boundary

MEAP currently contains an **authentication integration point**, not a completed login system.

- `MEAP_AUTH_ENABLED=false` returns the local development identity.
- `UserContext` is defined in `app/platform/auth/context.py`.
- `require_permission(...)` enforces server-side permissions when authentication is enabled.
- There are currently no provider routes, login page, session middleware, token verification, user store, or logout flow.
- The current enabled-auth fallback also returns the development identity when no session user exists. This must be changed to fail closed before authentication is enabled outside local development.

**Do not set `MEAP_AUTH_ENABLED=true` in a deployed environment until every item in section 3.5 is implemented and tested.** Merely changing that flag does not enable secure login.

### 3.1 Gmail and Outlook terminology

The login options should be presented as **Sign in with Google** and **Sign in with Microsoft**. Gmail and Outlook are mail products; the identity providers are Google Identity and Microsoft Entra ID.

For authentication only, request `openid profile email`. Do not request Gmail, Microsoft Graph mail, or calendar permissions unless a separate product feature genuinely needs them and has its own consent and security review.

Use the server-side OpenID Connect Authorization Code flow. Provider registration and protocol details are maintained in the official documentation:

- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [Microsoft identity platform OpenID Connect](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc)

### 3.2 Recommended configurable provider contract

Before implementing provider routes, extend `Settings` in `app/settings.py`. The following is the recommended contract; it is not present in the starter yet:

```python
from pydantic import SecretStr

# Authentication
auth_enabled: bool = False
auth_providers: tuple[Literal["google", "microsoft"], ...] = ()
auth_redirect_base_url: str = "http://127.0.0.1:8000"
auth_cookie_secure: bool = False

google_client_id: str = ""
google_client_secret: SecretStr | None = None

microsoft_client_id: str = ""
microsoft_client_secret: SecretStr | None = None
microsoft_tenant_id: str = "organizations"
```

Pydantic reads complex environment values as JSON. Examples:

```dotenv
# Google only
MEAP_AUTH_ENABLED=true
MEAP_AUTH_PROVIDERS='["google"]'
MEAP_GOOGLE_CLIENT_ID=...
MEAP_GOOGLE_CLIENT_SECRET=...

# Microsoft only
MEAP_AUTH_ENABLED=true
MEAP_AUTH_PROVIDERS='["microsoft"]'
MEAP_MICROSOFT_CLIENT_ID=...
MEAP_MICROSOFT_CLIENT_SECRET=...
MEAP_MICROSOFT_TENANT_ID=organizations

# Both providers
MEAP_AUTH_ENABLED=true
MEAP_AUTH_PROVIDERS='["google","microsoft"]'
```

Validate settings at startup: authentication requires at least one provider, and each enabled provider requires its own client ID and secret. Do not infer enabled providers from the presence of secrets. The explicit provider list is the source of truth for both routes and buttons.

`organizations` allows work or school Microsoft accounts from multiple Entra tenants. Use a specific tenant ID for a single-tenant enterprise deployment. Make that choice deliberately with the identity administrator.

### 3.3 Provider registration

Register one web application with each provider that may be enabled. Callback URLs must match exactly.

Recommended local callbacks:

```text
http://127.0.0.1:8000/auth/callback/google
http://127.0.0.1:8000/auth/callback/microsoft
```

Production callbacks use the public HTTPS origin. Do not use wildcard callbacks.

Use provider discovery rather than hard-coding authorization and token endpoints:

```text
Google:
https://accounts.google.com/.well-known/openid-configuration

Microsoft:
https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration
```

### 3.4 Recommended implementation layout

Authentication belongs to Platform, not to a business module:

```text
app/platform/auth/
├── context.py       # UserContext and fail-closed dependency
├── providers.py     # Google/Microsoft discovery and client configuration
├── routes.py        # login, provider start, callback, logout
├── session.py       # convert verified claims to/from server session state
└── templates/
    └── login.html   # renders only configured provider buttons
```

Implementation sequence:

1. Add an actively maintained OIDC client library and pin an accepted version in `pyproject.toml`.
2. Add `SessionMiddleware` in `create_app()`. Use a separate production-grade secret, `https_only=True` in production, `httponly`, and an appropriate `SameSite` policy.
3. Add `/auth/login`, `/auth/login/{provider}`, `/auth/callback/{provider}`, and `/auth/logout` routes.
4. Reject a provider name not listed in `settings.auth_providers`, even if credentials happen to exist.
5. Render provider buttons by iterating over `settings.auth_providers`. One configured provider produces one button; both produce two.
6. On login start, create and retain `state` and `nonce`; use PKCE when supported by the chosen library/provider.
7. On callback, validate `state`, exchange the code server-side, and verify the ID token signature, issuer, audience, expiration, and nonce.
8. Identify an account by the stable pair `(issuer, subject)`, not by email address. Email addresses can change and are not globally unique identity keys.
9. Map verified groups or application roles to MEAP permissions on the server. Never accept permissions from form data or query parameters.
10. Store only the minimum session data. Do not put provider tokens in local storage, HTML, URLs, or logs.
11. Build `request.state.user` as a `UserContext` for authenticated requests.
12. Make `get_current_user()` raise `AuthenticationError` or redirect browser page requests to login when auth is enabled and the session is absent or invalid. Never return `_DEV_USER` on that path.
13. Logout must clear the local session; add provider logout only if the deployment's sign-out requirements call for it.

If the application needs durable user preferences, role assignments, or audit ownership, add a platform user table keyed by issuer and subject. A display name or email is profile data, not the primary identity.

### 3.5 Authentication go-live checklist

Before enabling authentication:

- [ ] No enabled-auth path can return `_DEV_USER`.
- [ ] Unknown or disabled providers return 404 or a safe validation error.
- [ ] `state`, `nonce`, token signature, issuer, audience, and expiration are verified.
- [ ] Callback URLs are exact and production uses HTTPS.
- [ ] Cookies are signed, `HttpOnly`, `Secure` in production, and have an explicit `SameSite` policy.
- [ ] Session identifiers rotate after login and sessions expire.
- [ ] Secrets come from a secret manager and never appear in logs or source control.
- [ ] Only `openid profile email` is requested for login.
- [ ] Direct requests to protected endpoints are tested without a session and without the required permission.
- [ ] Login, callback failure, logout, timeout, and provider outage states have usable pages.
- [ ] Role-to-permission mapping is reviewed independently from navigation visibility.

## 4. Add a page, backend logic, and database persistence

First decide whether the work belongs in an existing module.

- Add a page to an existing module when it uses the same business vocabulary, permissions, lifecycle, and data ownership.
- Create a new module when it represents an independently understandable capability with its own route prefix and permissions.
- Put a capability in Platform only when substantially every module needs it. Platform must never import a business module.

### 4.1 Canonical module structure

```text
app/modules/vendor_review/
├── __init__.py
├── module.py       # identity, route, navigation, permission declarations
├── permissions.py  # module.resource.action constants
├── models.py       # SQLAlchemy persistence model and domain vocabulary
├── schemas.py      # validated input, query state, and template view models
├── repository.py   # reads, writes, query composition
├── service.py      # business rules and transaction orchestration
├── routes.py       # HTTP input/output only
├── jobs.py         # optional long-running work
└── templates/
    └── vendor_review/
```

Keep responsibility predictable:

| Concern | Location |
|---|---|
| Parse path, query, and form input; choose response | `routes.py` |
| Business rules and workflow transitions | `service.py` |
| SQLAlchemy reads, writes, filtering, sorting | `repository.py` |
| Tables, columns, relationships, enums | `models.py` |
| Request/query validation and view models | `schemas.py` |
| Server-rendered UI and HTMX fragments | `templates/` |
| Permission names | `permissions.py` |

Do not rename these layers to `manager.py`, `handler.py`, or `orchestrator.py`.

### 4.2 Implementation sequence

1. **Choose the page archetype.** Use List Report for a work queue, Object Page for one business object, and Sub-Object for focused detail. Follow the design language status semantics and density rules.
2. **Declare permissions** in `permissions.py` using `module.resource.action`, for example `vendor_review.vendor.view` and `vendor_review.vendor.approve`.
3. **Create models** in `models.py`. Use explicit constraints and indexes. Store authoritative state in the database, not in HTML or browser storage.
4. **Create schemas/view models** in `schemas.py`. Put navigable filters, sorting, and pagination in typed URL query state.
5. **Implement repository methods.** Whitelist sortable columns; never interpolate a user-supplied column name into SQL.
6. **Implement the service.** Put validation and workflow transitions here. Raise MEAP taxonomy errors with stable reason codes and safe messages.
7. **Implement routes.** Inject `Session` with `Depends(get_db)`, call the service, and use `render_page()` for pages or `render_fragment()` for an intentional HTMX fragment.
8. **Protect every operation** with `require_permission(...)`. Hiding a button or nav link is not authorization.
9. **Create templates.** Use native links and named form controls as the authoritative interaction. HTMX swaps ordinary light-DOM regions and enhances the native flow.
10. **Define `MODULE`** in `module.py` with a unique ID and route prefix.
11. **Register the module explicitly** by importing it and adding it to `MODULES` in `app/main.py`.
12. **Register its models for migrations** by importing the module's `models` in `migrations/env.py`.

Example route boundary:

```python
@router.post("/{vendor_id}/approve", name="vendor_review.approve")
async def approve_vendor(
    request: Request,
    vendor_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _permission=Depends(require_permission(VENDOR_APPROVE)),
):
    vm = VendorReviewService(db).approve(vendor_id, approved_by=user.user_id)
    return render_fragment(
        request,
        "vendor_review/fragments/status.html",
        {"vm": vm},
    )
```

### 4.3 Database migration workflow

Local/development/test profiles call `Base.metadata.create_all()` to make development startup convenient. That is not a substitute for migrations. Production uses Alembic.

After importing the new model in `migrations/env.py`:

```bash
source .venv/bin/activate

# Point MEAP_DATABASE_URL at the intended development database first.
alembic revision --autogenerate -m "add vendor review"

# Read the generated upgrade and downgrade functions before applying them.
alembic upgrade head
```

Never apply an unreviewed generated migration to shared or production data. Test destructive column changes, backfills, uniqueness constraints, and downgrades against a realistic copy of the schema.

### 4.4 Minimum tests for new functionality

Add tests for:

- Module contract, registration, navigation, and disabled behavior.
- Direct page load and the HTMX fragment response.
- Native form submission without HTMX-specific assumptions.
- Service rules, including invalid state transitions.
- Repository filtering, sorting, pagination, and database constraints.
- Anonymous access and insufficient permission when auth is enabled.
- Deep links, query-string state, and back/forward-safe URLs.
- Empty, loading, validation, system-error, and large-data table states.
- Responsive navigation and content at supported breakpoints.

Run:

```bash
source .venv/bin/activate
pytest tests/ -v
```

## 5. Debugging map

Start at the layer that owns the symptom:

| Symptom | Inspect first |
|---|---|
| Data is missing or sorted incorrectly | `repository.py`, then query schema |
| A workflow rule is wrong | `service.py` and domain enums |
| A button does nothing | native `href`/`action`, route, HTMX target, returned fragment |
| A full page appears inside the content area | route returned a page where a fragment was required, or targeted the wrong region |
| The screen is visually inconsistent | template classes, then `meap.css` tokens/components |
| Migration is empty | model import in `migrations/env.py` and model's shared `Base` |
| A user can call a hidden operation | missing `require_permission(...)` on the server route |
| Login silently becomes the dev user | auth integration is incomplete; make `get_current_user()` fail closed |
| Cause is unclear | follow the correlation ID through structured logs |

## 6. Frequently asked questions

### Why is my navigation item not showing?

Confirm that the module is imported and present in `MODULES`, `enabled=True`, and has a `NavigationDefinition`. Restart the process after changing module registration. A module with `navigation=None` can have routes without a sidebar link.

### Why does the route return 404 after I created a module?

The router is mounted only for modules registered in the explicit `MODULES` list. Also confirm that the router prefix and `ModuleDefinition.route_prefix` describe the same public route.

### Why is Alembic autogenerate producing an empty migration?

Import the new module's `models` in `migrations/env.py` and confirm those models inherit from `app.platform.database.base.Base`.

### Why is a whole shell nested inside the current page?

An HTMX action likely requested a route that returned `render_page()`. Use a dedicated fragment route and `render_fragment()` when replacing only part of the page. HTMX targets must be ordinary light-DOM elements.

### Why did an HTMX form omit a value?

Authoritative input must use native form controls with `name` attributes. Visual custom elements may enhance presentation but must not be the only source of submitted business data.

### Can hiding a navigation item or button secure an operation?

No. Navigation visibility is usability only. Protect the route with `require_permission(...)` and test the direct HTTP request.

### Can one business module import another?

No. Keep modules independently understandable. Move a truly shared, cross-cutting capability into Platform or communicate through an explicit stable boundary such as stored identifiers, jobs, or a platform service.

### Can I enable login by setting `MEAP_AUTH_ENABLED=true`?

Not yet. The starter exposes the integration boundary but does not include complete OIDC routes or verified sessions, and the current missing-user behavior does not fail closed. Implement and pass the go-live checklist first.

### Is “Gmail login” different from “Google login”?

Use Google Identity for login. Gmail API access is a separate permission set and is not needed for authentication. The equivalent distinction applies to Microsoft identity versus Outlook or Microsoft Graph mail access.

### How do I enable only Google, only Microsoft, or both?

Once the provider contract and routes in section 3 are implemented, set `MEAP_AUTH_PROVIDERS` to `["google"]`, `["microsoft"]`, or both values as JSON. The login page and accepted provider routes must read the same setting.

### Where should provider secrets live?

Use the deployment platform's secret manager. Local developers may use an uncommitted `.env`. Never put secrets in `module.py`, templates, JavaScript, migrations, test snapshots, or logs.

### How do I add a page to an existing module without adding navigation?

Add the route, service/repository behavior, and template within that module. Link to it from the module's List Report or Object Page. A navigation entry represents the module workspace, not every screen.

### How is compact/comfortable density customized?

Density belongs to the platform shell and design tokens, not business templates. Reuse the existing table/control classes so the shell's density setting applies consistently. Do not introduce a module-specific density mode.

### What should be stored in the URL?

Navigable view state: search, filters, sort, direction, page, selected tab, and object identifiers. Store authoritative business state in the database and short-lived interaction state in the browser.

## 7. Pull request review checklist

- [ ] The capability is in the correct module or Platform location.
- [ ] Navigation comes from `ModuleDefinition`; no business link was added to the shell.
- [ ] Routes contain HTTP concerns only.
- [ ] Business rules are in services and persistence is in repositories.
- [ ] Every mutation has a server-side permission dependency.
- [ ] URLs preserve navigable view state and work by direct load.
- [ ] Native controls and links remain authoritative when HTMX is unavailable.
- [ ] Models are imported by Alembic and the migration was reviewed.
- [ ] Templates follow the MEAP page archetypes and status semantics.
- [ ] Tests cover permissions, failure states, deep links, HTMX fragments, and responsive behavior.
- [ ] No credentials, tokens, private data, or provider claims are logged or committed.
