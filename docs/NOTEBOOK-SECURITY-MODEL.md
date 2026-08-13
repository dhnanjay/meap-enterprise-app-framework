# MEAP Notebook Security Model

**Status:** Normative foundation; execution not implemented

MEAP records notebook intent now so permissions, audit vocabulary, provenance,
and reproducibility do not need to be retrofitted later. It does not currently
start, proxy, embed, or execute Marimo or Jupyter.

## The governing rule

> Notebook edit permission is equivalent to local shell access on the MEAP server.

An editable notebook can read environment variables, application files,
database files, credentials visible to its process, and other accessible
workspaces. `platform.notebook.edit` is therefore platform-admin-only. It must
never be assignable through an organization-admin role or ordinary role editor.

## Current shipped boundary: registry only

`MEAP_NOTEBOOKS_ENABLED` defaults to `false`. Phase 1 includes only:

- The typed `platform_notebooks` registry table
- Eight stable `platform.notebook.*` permissions
- Append-only `platform_audit_events`
- Source checksum, runtime profile, and environment lock hash fields
- Validation for HTTPS external destinations and workspace-relative sources
- Migration and architecture/security tests

Phase 1 intentionally includes no notebook route, navigation item, iframe,
subprocess, port allocator, process registry, reverse proxy, WebSocket relay,
idle reaper, launch grant, data API, or optional Marimo/Jupyter dependency.
Setting the feature flag to `true` does not change that fact.

## Accepted delivery order

### Phase 2: external links

External notebook links may be added later with all of these controls:

- An exact deployment-configured hostname allowlist
- HTTPS only
- No MEAP token or cookie forwarded
- New-tab navigation
- An explicit `External` label
- No implicit access to MEAP data

External URLs are registry records, not arbitrary template strings or shell
commands.

### Phase 3: read-only Marimo applications

Only a named business use case should trigger this phase. The supported target
is an approved, parameterized application served with `marimo run`, not an
editor. It must use a separate browser origin and notebook session.

If an iframe is eventually used, `allow-scripts` and `allow-same-origin` may be
combined only because the notebook is cross-origin from MEAP. `allow-same-origin`
lets Marimo retain its own origin for storage and WebSockets; it does not make
the frame same-origin with MEAP. This reasoning must remain as a template comment
so a future maintainer does not accidentally move the frame onto the MEAP origin.

### Editable workspaces and JupyterHub

Deferred indefinitely. Revisit only for repeated requests from named users.
There is no notebook gateway in the current roadmap.

The sole exception is a trusted developer manually running `marimo edit` or
Jupyter locally. That is outside the MEAP application boundary and is not a
multi-user feature.

## Permissions

| Permission | Meaning |
|---|---|
| `platform.notebook.view` | View an approved notebook record or future read-only app |
| `platform.notebook.run` | Run an approved application when execution exists |
| `platform.notebook.edit` | Execute arbitrary code; platform-admin-only |
| `platform.notebook.create` | Create a registry draft |
| `platform.notebook.publish` | Activate an approved, reproducible definition |
| `platform.notebook.export` | Export approved output through the artifact service |
| `platform.notebook.manage` | Manage registry metadata and policy |
| `platform.notebook.data_access` | Use an explicitly scoped future data interface |

Hiding a link is never authorization. Every future route must enforce the
corresponding server-side permission.

## Registry rules

Registry records are typed as:

- Engine: `MARIMO` or `JUPYTER`
- Mode: `EXTERNAL`, `APPLICATION`, or `EDITABLE`
- Status: `DRAFT`, `ACTIVE`, or `DISABLED`

An external record requires an absolute HTTPS URL and cannot contain a local
source path. A local record requires a relative source path without `..` and
cannot contain an external URL. Marimo sources use `.py`; Jupyter sources use
`.ipynb`.

Executable definitions require:

- A source checksum
- A named, immutable runtime profile
- An environment lockfile hash

An editable definition must require `platform.notebook.edit`. Registration does
not imply that execution exists or is safe.

## Artifact lineage and reproducibility

A future notebook output used in a workpaper must be stored by the platform
artifact service. Writing a chart to an arbitrary directory or emailing it
outside the evidence chain is not an acceptable publication path.

Every future `notebook.runtime_started` audit event must record:

- Notebook source version/checksum
- Runtime profile or image identifier
- Environment lockfile hash
- Data snapshot identifier
- Input artifact IDs

Every published result must record output artifact IDs and preserve the
`original → normalized → results → report` lineage. Runtime outputs must never
bypass artifact checksum and provenance handling.

## Future process-state constraint

If process execution is ever approved, its registry cannot be an in-memory
dictionary. Multiple Uvicorn/Gunicorn workers would start duplicate processes
and see inconsistent leases. Process state, port allocation, leases, and
heartbeats must live in PostgreSQL or Redis, with a single elected reaper or
scheduled worker.

No process-lifecycle implementation is present today.

## Isolation terminology

MEAP recognizes only these honest modes:

- `local_trusted`: the editor has shell-equivalent access; trusted developer only
- `container_isolated`: a separately constrained local container or OS user

There is no `local_isolated` mode implemented by a second Python process under
the same operating-system user. That would not provide meaningful isolation.
Adding container isolation would be a separate deployment feature and would no
longer be satisfied by only `pip install -e .`.

## Browser and cookie boundary for a future Phase 3

Future embedded notebooks must use a separate origin, for example:

```text
https://app.example.com
https://notebooks.example.com
```

Both may resolve to the same machine. They must not share cookies. Local browser
testing should use locally trusted HTTPS certificates (for example, `mkcert`)
rather than relying on inconsistent `Secure` cookie behavior on HTTP localhost
subdomains.

MEAP's CSRF token and session cookie must never be forwarded to a notebook
process. A future notebook service must have its own session, CSRF validation,
origin validation, and WebSocket-origin validation.

## Audit vocabulary

The stable vocabulary includes:

```text
notebook.registered
notebook.updated
notebook.enabled
notebook.disabled
notebook.launched
notebook.runtime_started
notebook.runtime_stopped
notebook.exported
notebook.artifact_published
notebook.access_denied
```

Audit records never contain session tokens, provider credentials, database
passwords, complete notebook contents, or complete data extracts.

## Revisit criteria

Do not build execution infrastructure merely because the schema can describe it.
Advance beyond external links only when a named accounting user needs a specific
parameterized analysis that a normal MEAP module cannot reasonably provide.
