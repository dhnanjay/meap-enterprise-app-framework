# MEAP — Modular Enterprise Application Platform

**A server-first, configuration-assembled, modular enterprise application platform built on standard Python/web technologies.**

> **Business state lives in the database. Navigable view state lives in the URL. Ephemeral interaction state lives in the browser.**

---

## Quick Start

```bash
# Clone / enter the project
cd htmx_fastapi_starter_pack

# (Recommended) Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Create the first administrator (prints a 15-minute enrollment URL)
python -m app.platform.auth.cli bootstrap-admin \
  --email admin@example.com \
  --display-name "MEAP Administrator" \
  --organization "Example Organization"

# Run the app (local profile — SQLite, local TOTP, tables auto-created)
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v
```

Open `http://localhost:8000` in your browser.

---

## Developer Customization

Read [`docs/DEVELOPER-CUSTOMIZATION-GUIDE.md`](docs/DEVELOPER-CUSTOMIZATION-GUIDE.md) before extending the starter. It documents the repository's actual extension points for:

- Configuring, ordering, hiding, and disabling navigation entries
- Operating the built-in administrator-issued TOTP login and its future OIDC boundary
- Adding a page or complete module with routes, services, repositories, templates, permissions, and database models
- Generating and reviewing Alembic migrations
- Testing, debugging, and frequently encountered integration failures

> **Authentication:** MEAP includes self-hosted, administrator-issued TOTP login with encrypted credentials, recovery codes, server-side sessions, CSRF protection, and fail-closed access. It sends no email and does not verify mailbox ownership. Read [`docs/AUTHENTICATION-OPERATIONS.md`](docs/AUTHENTICATION-OPERATIONS.md) before deployment.

---

## What Is MEAP?

MEAP is an opinionated starter platform for building **long-lived enterprise applications** — accounting workflows, financial-data processing, reconciliations, audit testing, evidence collection, workflow review, and more.

It provides one core guarantee:

> An engineer who understands one MEAP application should understand the structure, extension points, and debugging path of **every** MEAP application.

### Design Priorities (in order)

1. **Predictability**
2. **Modularity**
3. **Maintainability**
4. **Debuggability**
5. **Traceability**
6. **Enterprise UI consistency**
7. **Developer productivity**
8. **Performance**
9. **Extensibility**
10. **Novelty**

When priorities conflict, MEAP prefers the earlier item.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Web Framework | FastAPI |
| Templating | Jinja2 |
| Client Interaction | HTMX |
| UI Components | Semantic HTML + custom CSS design system (see note below) |
| Database | PostgreSQL (SQLite for local/test) |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Background Jobs | Celery + Redis (dev runner included) |
| Testing | Pytest |

---

## UI Architecture: Reliability Before Decoration

MEAP uses a three-tier UI boundary:

1. **Native semantics** — `<a>`, `<form>`, `<input>`, `<select>`, `<textarea>`, `<button>`, and `<input type="file">` carry navigation and authoritative business input.
2. **Enterprise presentation** — the MEAP CSS vocabulary provides the shell, cards, tables, statuses, spacing, loading, empty, and error states.
3. **Certified rich islands** — UI5 Web Components may be introduced for presentation or advanced interaction only after the specific component passes browser compatibility tests for the use case.

This is deliberately more precise than saying either “UI5 everywhere” or “never use Web Components.” Modern form-associated custom elements have useful standards support, but HTMX and custom-element interoperability has had real edge cases. MEAP therefore does not make an uncertified custom element responsible for transmitting authoritative state.

The isolation rule is simple:

> HTMX swaps ordinary light-DOM regions. It never targets inside a component's Shadow DOM.

Native forms retain `action`, `method`, and named controls, while links retain `href`. They therefore continue to work when HTMX or application JavaScript is unavailable. HTMX 2.0.10 is pinned and served locally from `app/platform/static/vendor/`; the application has no runtime CDN dependency.

| Responsibility | Default owner |
|---|---|
| Navigation and deep links | Native `<a href>` |
| GET/POST business input | Native forms and controls |
| URL query state | Server + native URL |
| Fragment replacement | HTMX targeting light DOM |
| Enterprise visual language | MEAP CSS design layer |
| Rich component behavior | Individually certified UI island |

The intended compatibility harness covers direct load, HTMX navigation, GET and POST forms, multipart upload, repeated swaps, validation, back/forward restoration, sorting, pagination, and responsive navigation. A UI component becomes a platform default only after those relevant behaviors pass.

### Design language references

- Open [`docs/meap-styleguide.html`](docs/meap-styleguide.html) for live examples of the supported tokens, status semantics, object page, list report, controls, and writing patterns.
- Read [`docs/MEAP-DESIGN-LANGUAGE.md`](docs/MEAP-DESIGN-LANGUAGE.md) for the normative archetype rules and non-negotiable review checks.
- Use [`docs/DEVELOPER-CUSTOMIZATION-GUIDE.md`](docs/DEVELOPER-CUSTOMIZATION-GUIDE.md) for navigation, authentication-provider configuration, new modules/pages, migrations, tests, and FAQs.


## Architecture Overview

```
BROWSER
  Semantic HTML + CSS Design System + Jinja + HTMX
        │
        ▼ HTTP
PLATFORM CORE
  Shell • Registry • Auth • Permissions • Database
  Jobs • Artifacts • Errors • Diagnostics • Query State
        │
   ┌────┼────┐
   ▼    ▼    ▼
MODULE A   MODULE B   MODULE C
  routes.py     routes.py     routes.py
  service.py    service.py    service.py
  repository.py repository.py repository.py
  models.py     models.py     models.py
  jobs.py       jobs.py       jobs.py
  templates/    templates/    templates/
        │
        ▼
INFRASTRUCTURE
  PostgreSQL • Worker/Queue • Object Storage • External APIs
```

### The Core Rule: Platform vs Module

There are exactly **two conceptual levels**:

- **Platform** — capabilities needed by substantially every application (shell, auth, database, jobs, artifacts, errors, etc.)
- **Modules** — business capabilities (bank reconciliation, JE review, process evidence, etc.)

The Platform **never** imports from business modules. Modules consume Platform functionality.

---

## Repository Structure

```
meap/
├── app/
│   ├── main.py                    # Entry point + module registration (§9)
│   ├── settings.py                # Typed configuration (§55)
│   ├── middleware/
│   │   └── correlation.py         # Correlation ID middleware (§46)
│   ├── platform/
│   │   ├── shell/                 # Application shell + navigation (§11,12)
│   │   ├── registry/              # Module registry + definitions (§8,9)
│   │   ├── auth/                  # Authentication context (§40)
│   │   ├── permissions/           # Authorization (§41)
│   │   ├── database/              # SQLAlchemy base + session (§43)
│   │   ├── jobs/                  # Job model + service (§32-34)
│   │   ├── artifacts/             # Artifact model + storage (§35-38)
│   │   ├── audit/                 # Append-only audit events
│   │   ├── notebooks/             # Registry + policy only; no execution
│   │   ├── diagnostics/           # /developer area (§48)
│   │   ├── errors/                # Error taxonomy + handlers (§44,45)
│   │   ├── query_state/           # URL-state helpers (§URL-State)
│   │   ├── templates/             # render_page + shell templates (§17)
│   │   └── static/                # CSS design layer + JS (§22)
│   └── modules/
│       ├── bank_reconciliation/   # Example module (§70)
│       │   ├── module.py          # ModuleDefinition
│       │   ├── routes.py          # HTTP endpoints
│       │   ├── service.py         # Business logic
│       │   ├── repository.py      # Database operations
│       │   ├── models.py          # SQLAlchemy models
│       │   ├── schemas.py         # View models + request schemas
│       │   ├── jobs.py            # Background job definitions
│       │   ├── permissions.py     # Permission constants
│       │   └── templates/         # Jinja templates
│       └── journal_entry_review/  # Example module
│           └── ...
├── tests/                         # Test suite (§59)
├── migrations/                    # Alembic migrations (§68)
└── pyproject.toml
```

**Same responsibility → same location.** Developers may not rename `service.py` to `manager.py`, `orchestrator.py`, or any synonym.

---

## Module Contract

Every module implements a typed `ModuleDefinition`:

```python
# app/modules/bank_reconciliation/module.py

MODULE = ModuleDefinition(
    id="bank_reconciliation",
    name="Bank Reconciliation",
    route_prefix="/bank-recon",
    description="...",
    router=router,
    navigation=NavigationDefinition(
        label="Bank Reconciliation",
        icon="compare",
        group="Accounting",
        order=20,
    ),
    permissions=(
        "bank_reconciliation.reconciliation.view",
        "bank_reconciliation.reconciliation.create",
        ...
    ),
    enabled=True,
)
```

The module definition says:

> I exist. My name is X. My route is /x. Place me under group Y. These are my permissions. Mount this router.

**Nothing more.**

---

## Adding a New Module

```bash
# 1. Create the module directory
mkdir app/modules/my_feature

# 2. Implement the canonical files
#    module.py, routes.py, service.py, repository.py
#    models.py, schemas.py, jobs.py, permissions.py, templates/

# 3. Register in app/main.py (the EXPLICIT module list)
MODULES: list[ModuleDefinition] = [
    BankReconciliationModule,
    JournalEntryReviewModule,
    MyFeatureModule,           # ← add here
]
```

That's it. Navigation, routes, permissions, and shell integration happen automatically.

**Adding a module should NOT require editing:**
- Global sidebar HTML
- Global authentication code
- Global routing switch statements
- Other business modules

---

## Module Enable / Disable

Disable a module by setting `enabled=False` in its `module.py`. A disabled module cleanly disappears:

- ✅ Navigation removed
- ✅ Routes unavailable
- ✅ Permissions not exposed
- ✅ No impact on other modules

---

## URL-as-State Architecture

The URL is the canonical representation of navigable view state:

```
/bank-recon/BR-2026-004/exceptions
    ?status=unmatched
    &account=10245
    &min_amount=10000
    &sort=amount
    &direction=desc
    &page=3
```

Paste that URL in a new tab tomorrow → the same view is reconstructed from the server.

### Query State Helpers

```python
from app.platform.query_state.helpers import PageQuery, query_url, SortMapper

# Modules extend PageQuery for module-specific filters
class ExceptionQuery(PageQuery):
    status: str | None = None
    min_amount: Decimal | None = None

# Sort securely — never pass user input directly to SQL
mapper = SortMapper(
    allowed={"amount": Exception.amount, "date": Exception.date},
    default=Exception.created_at,
)
column = mapper.resolve(query.sort)
```

---

## Server-First Rendering

The canonical screen lifecycle:

```
URL → FastAPI route → Service → Repository → Typed View Model → Jinja → HTML → Browser
```

The browser does **not** maintain a duplicate copy of authoritative business state.

### Full Page vs Fragment

Every route uses `render_page()` which automatically detects HTMX requests:

```python
@router.get("/{reconciliation_id}")
def detail(request: Request, reconciliation_id: str):
    vm = service.get_detail(reconciliation_id)
    return render_page(request, "detail.html", {"vm": vm})
```

- **Normal request** → full document (shell + content)
- **HTMX request** → content fragment only

No per-endpoint `if request.headers.get("HX-Request")` needed.

---

## Error Taxonomy

Errors follow a structured envelope (§45):

```json
{
  "error_id": "ERR-39218",
  "correlation_id": "CORR-...",
  "module": "bank_reconciliation",
  "operation": "normalize_source",
  "category": "DATA",
  "reason_code": "MISSING_REQUIRED_COLUMN",
  "safe_message": "...",
  "timestamp": "2026-..."
}
```

Categories: `VALIDATION`, `AUTHENTICATION`, `AUTHORIZATION`, `NOT_FOUND`, `CONFLICT`, `DOMAIN`, `DATA`, `INTEGRATION`, `JOB`, `ARTIFACT`, `SYSTEM`.

---

## Diagnostics

Visit `/developer` (available in local/dev/test profiles) to see:

- Registered modules
- Routes
- Permissions
- Configuration
- Job status
- Database connectivity

---

## Configuration

Settings are loaded from environment variables with typed defaults (§55):

| Variable | Default | Description |
|----------|---------|-------------|
| `MEAP_PROFILE` | `local` | Deployment profile |
| `MEAP_APP_NAME` | `MEAP` | Product name |
| `MEAP_DEBUG` | `false` | FastAPI debug mode |
| `MEAP_SECRET_KEY` | local-only development value | Application signing secret; replace outside local development |
| `MEAP_AUTH_ENABLED` | `true` | Enable self-hosted local TOTP authentication; set `false` only for trusted local development |
| `MEAP_AUTH_METHOD` | `local_totp` | Active authentication adapter |
| `MEAP_ADMISSION_MODE` | `invite_only` | Administrator-issued enrollment; `disabled` stops new enrollment |
| `MEAP_ALLOWED_EMAIL_DOMAINS` | empty | Optional comma-separated restriction on administrator-asserted addresses |
| `MEAP_SESSION_HMAC_KEY` | local-only value | Independent server-side session token HMAC key |
| `MEAP_CSRF_KEY` | local-only value | Independent signing key for short-lived pre-authentication form tokens |
| `MEAP_TOKEN_HMAC_KEY` | local-only value | Independent enrollment/recovery token HMAC key |
| `MEAP_CREDENTIAL_ENCRYPTION_KEY` | local-only value | Base64-encoded 32-byte AES-GCM key for TOTP seeds |
| `MEAP_CREDENTIAL_ENCRYPTION_KEYS` | empty | Production JSON keyring mapping key IDs to base64 AES-GCM keys |
| `MEAP_CREDENTIAL_ENCRYPTION_KEY_ID` | `local-v1` | Version identifier used for credential-key rotation |
| `MEAP_DATABASE_URL` | `sqlite:///./meap.db` | Database URL |
| `MEAP_DEVELOPER_AREA_ENABLED` | `true` | Enable `/developer` diagnostics |
| `MEAP_REDIS_URL` | empty | Redis/RQ connection; empty uses local background execution |
| `MEAP_ARTIFACT_STORAGE_BACKEND` | `local` | Artifact storage backend |
| `MEAP_ARTIFACT_STORAGE_PATH` | `./artifacts` | Local artifact directory |
| `MEAP_NOTEBOOKS_ENABLED` | `false` | Notebook metadata capability; does not enable execution |

See the [authentication operations guide](docs/AUTHENTICATION-OPERATIONS.md) for bootstrap and production-key configuration. External Google/Microsoft/Keycloak OIDC remains a future adapter and is not required for local TOTP.

---

## Running Tests

```bash
# Full test suite
pytest tests/ -v

# Specific test categories
pytest tests/test_platform.py -v      # Platform + registry + query state + errors
pytest tests/test_routes.py -v        # Route + contract + integration tests
pytest tests/test_architecture.py -v  # Architecture fitness tests (§61)
```

### Test Pyramid (§59)

- **Unit tests** — domain rules, services, parsing, matching
- **Repository tests** — queries, transactions, persistence
- **Route tests** — HTTP status, authorization, rendering
- **Contract tests** — module registration, navigation, permissions
- **Integration tests** — upload, process, review workflows

### Architecture Fitness Tests (§61)

The test suite enforces architectural rules:
- Modules cannot import other modules' internals
- Permissions are unique
- Navigation groups are valid
- Disabled modules don't break unrelated modules

---

## Background Jobs

MEAP uses Celery + Redis for durable background processing (§32). A dev runner is included for local development without Redis:

```bash
# Production: run Celery worker + Redis
celery -A app.platform.jobs.worker worker --loglevel=info

# Local dev: synchronous job runner (no Redis needed)
# Jobs run inline — see app/platform/jobs/dev_runner.py
```

Every job gets a durable Run record with status tracking (§33):

```
QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED
```

---

## Artifacts

Artifacts are a Platform concept (§37). An artifact represents files: workbooks, reports, screenshots, PDFs, evidence packages.

```python
artifact = artifact_service.create_artifact(
    filename="GL_2026.xlsx",
    artifact_type="source_workbook",
    storage_uri="...",
    content_type="application/vnd.openxmlformats",
    size=1024000,
    checksum="sha256:...",
    created_by=user.user_id,
    module="bank_reconciliation",
    metadata={"period": "2026-01"},
)
```

Artifact lineage tracks provenance: original → normalized → results → report.

---

## Notebook foundation

MEAP includes a disabled-by-default notebook registry and security vocabulary.
It does **not** currently launch, proxy, embed, or execute Marimo or Jupyter.

The governing rule is:

> Notebook edit permission is equivalent to local shell access on the MEAP server.

Read [`docs/NOTEBOOK-SECURITY-MODEL.md`](docs/NOTEBOOK-SECURITY-MODEL.md) before
adding any notebook link, application, dependency, route, or runtime behavior.
The accepted roadmap stops at registry metadata, external links, and a future
named use case for read-only `marimo run` applications. Editable workspaces and
JupyterHub are deferred.

---

## Key Architectural Principles

1. **Configuration determines what exists; code determines how it works.**
2. **Business state → PostgreSQL. Navigable view state → URL. Ephemeral UI → browser.**
3. **Same responsibility → same location.**
4. **A disabled module must disappear cleanly.**
5. **Adding a module should not require editing unrelated code.**
6. **Every screen has a stable URL.**
7. **Ordinary workflows function without HTMX.**
8. **HTMX enhances — it doesn't become the only path.**
9. **AI-generated code receives no architectural exemption.**

---

## Debugging Matrix (§49)

| Problem | Where to look |
|---------|--------------|
| Module missing | Registry / configuration |
| Navigation missing | Module definition → Registry → Shell |
| Route missing | Module router registration |
| Page not rendering | Route → `render_page` → Template |
| Wrong displayed value | View model → Template |
| Wrong business result | Service / Domain |
| Wrong persisted data | Repository |
| Upload failed | Upload route → Artifact storage |
| Pipeline failed | Job/Run → Service |
| Permission denied | Authorization policy |
| Artifact missing | Artifact service / storage |
| UI interaction broken | HTMX target/swap or UI5 event |
| System-wide failure | Platform / infrastructure |

---

## License

This is a starter pack. Adapt freely for your enterprise applications.
