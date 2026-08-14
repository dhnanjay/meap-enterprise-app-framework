# Optional LLM Module Generator — Parked Roadmap

**Status:** design direction only; not implemented
**Default:** disabled
**Intended operator:** workspace administrator or developer with explicit generation permission

## Goal

A future administrator should be able to describe a new capability in plain language. An optional LLM-assisted generator should understand MEAP's platform/module boundary, design language, registered navigation and permissions, database models, migration history, testing rules, and documentation contract, then produce a complete reviewable change set.

“Seamless” must not mean that a model edits a running production application without review. The safe unit of output is a proposed source-code patch with migrations, tests, and documentation that a person can inspect, validate in an isolated workspace, and explicitly approve.

## Required architecture context

The generator will consume a versioned, machine-readable context package assembled from the repository:

- Module contract and canonical file locations.
- Registry metadata, navigation contract, and permission catalog.
- SQLAlchemy metadata and current Alembic revision graph.
- Quiet Enterprise design tokens, components, and page archetypes.
- Authentication, organization ownership, audit, job, artifact, and notebook security rules.
- Existing modules as examples, with business records excluded unless the operator explicitly supplies safe sample data.
- Test and documentation requirements from the developer guides.

This package must be generated from source-of-truth code and schemas rather than maintained as a second handwritten description that can drift.

## Proposed workflow

1. An authorized administrator describes the desired functionality and acceptance criteria.
2. MEAP converts the request into a structured proposal: module name, pages, permissions, data entities, workflows, and migration impact.
3. The operator reviews and edits the proposal before generation.
4. The selected provider adapter generates files only inside an isolated worktree or disposable build workspace.
5. MEAP runs formatting, static checks, tests, migration upgrade/downgrade checks, schema-drift checks, and security policy checks.
6. The UI displays a file-by-file diff, migration plan, permission changes, test evidence, and unresolved warnings.
7. A human explicitly approves export or merge. Production never self-modifies.
8. The generation request, provider/model metadata, context-package version, output hash, validation results, and approval are audited without storing credentials or unnecessary business data.

## Provider boundary

LLM integration should be an adapter, not a platform dependency. A deployment may configure one provider, a local model, or no provider at all. Provider credentials remain in deployment secrets and are never stored in module tables or sent to the browser. The provider adapter must support data-redaction policy, request limits, timeouts, and an allowlist of context files.

The generator must remain independent per MEAP application. A new application can choose its own provider, model, keys, policy, and context package without sharing identity or generated state with another installation.

## Non-negotiable controls

- Disabled unless explicitly configured.
- Separate `module_generator.use` and `module_generator.approve` permissions.
- Administrator reauthentication before generation and approval.
- No direct writes to the active production source tree or database.
- No arbitrary shell access granted to the model.
- Generated migrations are reviewed and exercised against disposable databases.
- Organization ownership, route authorization, CSRF, audit, and output encoding are generated and tested by default.
- New navigation and dashboard entries must come from the module registry, preserving the existing discovery behavior.
- Secrets, authentication credentials, recovery codes, enrollment links, session tokens, and raw production records are excluded from prompts.
- Every generated change remains understandable and maintainable without the LLM.

## Delivery phases

1. Context-package exporter and drift test.
2. Deterministic module scaffolder without an LLM.
3. Proposal schema and review UI.
4. Optional provider adapter and isolated generation workspace.
5. Validation pipeline and diff viewer.
6. Explicit approval/export workflow with complete audit evidence.

The deterministic scaffolder should come first. It proves the extension contract and creates a reliable fallback before probabilistic generation is introduced.
