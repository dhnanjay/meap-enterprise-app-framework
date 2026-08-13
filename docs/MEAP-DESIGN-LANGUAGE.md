# MEAP Design Language — Quiet Enterprise

**Status:** v1, normative
**Applies to:** `app/platform/static/css/meap.css` and every `app/modules/*/templates/` directory
**Living reference:** `docs/meap-styleguide.html`

## 1. Decision

MEAP uses native HTML for authoritative web semantics and a dependency-free CSS design layer for enterprise presentation. Rich component islands may be certified separately, but they do not own navigation, form serialization, or HTMX swap targets by default.

The visual direction is **Quiet Enterprise**: one accent color, one UI type family plus a machine-identity face, hairline borders, no shadows on page content, and status hue used sparingly enough to remain meaningful.

## 2. Page archetypes

Every screen is one of three archetypes. A fourth requires a platform decision.

### Launchpad

Used for `/` and module indexes. It presents authorized workspaces and platform status. It has no greeting or decorative hero.

### List Report

Used for work queues and collections:

```text
breadcrumb
page header: context · title · actions
filter bar: writes to the URL
applied filters: reflects URL state
table: compact rows, figures right, status near the end
pagination
```

### Object Page

Used for one record:

```text
breadcrumb
page header: mono identity · subtitle · status · actions
facts strip: 3–5 defining values
tabs: each is a stable URL
content sections
```

Sub-collections such as exceptions remain List Reports nested beneath an Object Page URL.

## 3. Color semantics

Accent blue means **interactive**. It is limited to links, focus rings, primary buttons, the selected tab, and the current navigation item.

Status color means **record state**:

| Status | Meaning | Examples |
|---|---|---|
| neutral | Exists; no work underway | Draft, Not started, Cancelled |
| progress | Work underway; no decision | Queued, Running, In review |
| success | Resolved; nothing further needed | Cleared, Matched, Succeeded, Approved |
| attention | A person must explain or act | Unmatched, Open exception, Overdue, Unexplained difference |
| critical | The system could not complete work | Job failed, Integration error, System error |

An unexplained reconciliation difference is **attention**, never critical. Red is reserved for system failure and explicitly destructive/rejected outcomes.

Error taxonomy mapping:

- `VALIDATION`, `DOMAIN`, `DATA`, `CONFLICT` → attention
- `INTEGRATION`, `JOB`, `SYSTEM`, `ARTIFACT` → critical
- `NOT_FOUND`, `AUTHORIZATION`, `AUTHENTICATION` → neutral

## 4. Typography

Use Inter for everything a person reads. Use IBM Plex Mono only for machine identity: record IDs, correlation IDs, error IDs, reason codes, checksums, storage URIs, account numbers, and GL codes.

Money and dates remain in the UI face with `tabular-nums`. Typeface is a semantic signal: mono means “this exact string can be transcribed into a support ticket.”

Scale: 11 / 12 / 13 / 14 / 16 / 20 / 28px. Weights: 400 / 500 / 600. No 700 and no decorative italics.

## 5. Density

Two modes, persisted locally per user through `data-density` on `<body>`:

- `compact` — 36px data rows and 32px controls; default
- `comfortable` — 44px data rows and 36px controls

Do not add a third mode.

## 6. Writing

Copy names work in accounting language and states exactly what an action does.

| Avoid | Use |
|---|---|
| Good to see you. | Workspaces, Reconciliations, or the current queue name |
| Submit | Submit for review |
| Total exceptions | Open exceptions |
| Difference | Unexplained difference |
| Something went wrong | State the exact safe failure and next action |
| No data available | State how to create or reveal the data |

## 7. Non-negotiables

1. No hex, px, or rem literals in module templates. Values come from tokens.
2. No `box-shadow` on page content. Shadows are overlays only.
3. Border radius never exceeds 6px.
4. Every figure column uses tabular numerals and right alignment.
5. Accent blue appears only on interactive elements.
6. Exactly five status colors exist; new states map onto them.
7. One primary button per screen region.
8. Every module uses the three page archetypes.
9. Focus is always visible.
10. Every screen works with JavaScript disabled.

## 8. Print and workpapers

Reconciliation and JE review screens are printable evidence. Print output removes shell chrome, filters, actions, and pagination; retains object identity and facts; repeats table headers; darkens borders; and prevents record rows from splitting where practical.

## 9. Out of scope for v1

- Dark mode
- A third density mode
- Decorative animation
- A general icon set

Vendor the Inter and IBM Plex Mono WOFF2 subsets before production. Runtime CDN fonts are not permitted by MEAP’s reproducible-assets policy.
