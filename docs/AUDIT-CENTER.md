# MEAP Audit Center

**Status:** administrator-only read model  
**Route:** `/audit`  
**Scope:** the signed-in administrator's workspace

## Purpose

Audit Center is a separate Platform panel for security, access, and operational evidence. It is not embedded in Users because an event history grows much faster than an account list and needs its own compact list-report workflow.

Workspace administrators can:

- Search by event type, correlation ID, entity identifier, or actor.
- Filter by exact event type, outcome, actor, and inclusive date range.
- Page through 25, 50, or 100 newest-first events.
- Open a dedicated event page with actor, entity, correlation, runtime, notebook, artifact, and event-data context.

The first version is intentionally read-only. It has no browser endpoint for editing or deleting audit events.

## Security boundary

The sidebar link is convenience only. Both `/audit` and `/audit/{event_id}` require the effective `workspace_admin` role at the server route.

Every list, facet, search, count, and detail query includes `organization_id` in SQL. An event identifier from another workspace returns not found; it is never loaded globally and filtered afterward.

The `(organization_id, occurred_at)` database index supports the primary newest-first workspace timeline without scanning unrelated organizations.

## Event-writing rules

Use `AuditService.record()` for security- or business-significant changes. Event data may describe the change, but must never contain:

- Passwords, TOTP secrets, recovery codes, session tokens, enrollment tokens, or CSRF tokens.
- Full source datasets or notebook outputs.
- Unnecessary personal or confidential values when stable identifiers are sufficient.

Prefer a stable `event_type`, the signed-in `organization_id` and `actor_user_id`, an entity type and identifier, and the request correlation ID. Notebook execution must also supply the reproducibility fields defined by the notebook security model.

## Current boundary

- Access is workspace-administrator only; it is not part of the configurable business-application matrix.
- Export, retention configuration, archive storage, and cryptographic tamper evidence are not implemented yet.
- The table is designed for screen review and filtering. A controlled CSV evidence export should be a later, separately permissioned increment.
- Database operators still control backup and retention at the storage layer.
