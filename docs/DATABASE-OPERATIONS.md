# MEAP Database Operations

**Status:** normative operator guide  
**Default local database:** SQLite (`meap.db`)  
**Schema authority:** Alembic migrations

MEAP no longer relies on SQLAlchemy `create_all()` to upgrade a running local installation. `create_all()` can create a missing table, but it cannot add or transform columns in an existing table. Every runnable local, development, and production database must match the current Alembic revision.

## Everyday commands

Run commands from the repository directory with the virtual environment active:

```bash
source .venv/bin/activate

# Read-only: show current and expected revisions.
meap db status

# Safe local upgrade: create a SQLite backup, then migrate to head.
meap db upgrade
```

If the project has not yet been installed into the active virtual environment, use the equivalent source form: `python -m app.platform.database.cli <status|upgrade|downgrade>`.

Example successful status:

```text
Current revision: 3836580891fe
Expected head: 3836580891fe
Status: current
```

When SQLite contains data, `upgrade` first creates a sibling backup such as:

```text
meap.before-upgrade-20260813-193000.db
```

The command uses SQLite's online backup API rather than copying a potentially inconsistent open file. Even so, stop Uvicorn before changing schema:

```bash
# Stop the app with Control-C, then:
meap db upgrade
uvicorn app.main:app --reload --port 8000
```

## First installation

Either run the database upgrade explicitly before bootstrap:

```bash
meap db upgrade
python -m app.platform.auth.cli bootstrap-admin \
  --email admin@example.com \
  --display-name "MEAP Administrator" \
  --organization "Example Organization"
```

Or run `bootstrap-admin` directly. Authentication host commands call the same safe upgrade service before accessing authentication tables. An existing SQLite database is backed up when an upgrade is required.

## Startup behavior

- Local, development, and production startup validate the database revision before serving routes.
- A behind, empty, or unversioned database fails startup with the exact upgrade command.
- Test profile databases remain isolated and use in-memory metadata creation.
- `/developer/health` reports the current and expected database revisions.

This prevents a stale schema from appearing as broken page navigation or delayed SQL errors.

## Recognized legacy local databases

Historical MEAP local startup created tables without recording an Alembic revision. The upgrade service recognizes only narrow, known MEAP schema fingerprints. It creates a backup, stamps the compatible historical revision, and applies later migrations.

An unknown unversioned schema is never stamped automatically. The command stops with:

```text
Database has tables but no recognized Alembic revision. Refusing to stamp it automatically.
```

Do not work around that protection with an arbitrary `alembic stamp`. Inspect the database and establish its real schema provenance first.

## Downgrade and recovery

Downgrade requires an explicit target revision:

```bash
meap db downgrade \
  --revision 4bd8a81af4b4
```

SQLite is backed up first. Downgrade is primarily for migration verification and controlled recovery, not ordinary feature rollback. Application code may not run against an older schema.

To recover SQLite from an automatic backup:

1. Stop Uvicorn.
2. Keep the failed database for investigation by moving it to a unique filename.
3. Copy the chosen backup into the configured database path.
4. Run `status` before restarting the matching application version.

Never overwrite the only copy of a database.

## PostgreSQL

Set `MEAP_DATABASE_URL` to the PostgreSQL SQLAlchemy URL before running the same status or upgrade command. MEAP does not create PostgreSQL backups. Use the deployment platform's snapshot facility or `pg_dump` before migration. Validate restore procedures separately.

The migration service, startup guard, and health status are database-neutral. SQLite backup creation is intentionally backend-specific.

## Release checklist

- [ ] Stop application and workers that write to the schema.
- [ ] Confirm `MEAP_DATABASE_URL` points to the intended database.
- [ ] Create or verify a recoverable backup.
- [ ] Run `meap db status`.
- [ ] Run `meap db upgrade`.
- [ ] Run status again and confirm `Status: current`.
- [ ] Start MEAP and check `/developer/health`.
- [ ] Exercise one read and one safe write in each affected module.
- [ ] Retain the pre-upgrade backup according to the deployment's retention policy.
