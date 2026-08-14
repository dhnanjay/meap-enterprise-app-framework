"""Database revision status, safe upgrades, backups, and startup enforcement."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url

from app.platform.database.base import make_engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


class DatabaseRevisionError(RuntimeError):
    """Raised when application code and database schema revisions differ."""


@dataclass(frozen=True)
class MigrationStatus:
    current_revisions: tuple[str, ...]
    head_revisions: tuple[str, ...]
    inferred_revision: str | None
    table_count: int

    @property
    def is_current(self) -> bool:
        return bool(self.current_revisions) and set(self.current_revisions) == set(
            self.head_revisions
        )

    @property
    def is_empty(self) -> bool:
        return self.table_count == 0

    @property
    def current_label(self) -> str:
        if self.current_revisions:
            return ",".join(self.current_revisions)
        if self.inferred_revision:
            return f"unversioned (compatible with {self.inferred_revision})"
        return "unversioned"

    @property
    def head_label(self) -> str:
        return ",".join(self.head_revisions)


@dataclass(frozen=True)
class MigrationResult:
    previous: MigrationStatus
    current: MigrationStatus
    backup_path: Path | None
    stamped_revision: str | None = None


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["meap_database_url"] = database_url
    return config


def _heads(database_url: str) -> tuple[str, ...]:
    script = ScriptDirectory.from_config(alembic_config(database_url))
    return tuple(sorted(script.get_heads()))


def _infer_unversioned_revision(engine: Engine, tables: set[str]) -> str | None:
    """Recognize schemas created by historical local ``create_all()`` startup.

    This is deliberately a narrow project-specific fingerprint. Unknown schemas
    are never stamped automatically.
    """
    if not tables:
        return None
    inspector = inspect(engine)
    if "br_reconciliations" not in tables:
        return None
    reconciliation_columns = {
        column["name"] for column in inspector.get_columns("br_reconciliations")
    }
    if "organization_id" in reconciliation_columns and {
        "auth_access_roles",
        "auth_membership_permissions",
    }.issubset(tables):
        return _heads(str(engine.url))[0]
    if "auth_organizations" in tables and "auth_sessions" in tables:
        return "4bd8a81af4b4"
    if "platform_notebooks" in tables and "platform_audit_events" in tables:
        return "b82e7c341a10"
    if {"platform_jobs", "platform_artifacts", "platform_evidence"}.issubset(tables):
        return "fa11f6602989"
    return None


def get_migration_status(
    database_url: str,
    *,
    engine: Engine | None = None,
) -> MigrationStatus:
    sqlite_path = _sqlite_path(database_url)
    if sqlite_path is not None and not sqlite_path.exists():
        return MigrationStatus(
            current_revisions=(),
            head_revisions=_heads(database_url),
            inferred_revision=None,
            table_count=0,
        )
    owns_engine = engine is None
    selected_engine = engine or make_engine(database_url)
    try:
        with selected_engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            current = tuple(
                sorted(MigrationContext.configure(connection).get_current_heads())
            )
        inferred = None if current else _infer_unversioned_revision(selected_engine, tables)
        return MigrationStatus(
            current_revisions=current,
            head_revisions=_heads(database_url),
            inferred_revision=inferred,
            table_count=len(tables - {"alembic_version"}),
        )
    finally:
        if owns_engine:
            selected_engine.dispose()


def _sqlite_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def backup_sqlite_database(database_url: str) -> Path | None:
    source_path = _sqlite_path(database_url)
    if source_path is None or not source_path.exists() or source_path.stat().st_size == 0:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = source_path.with_name(
        f"{source_path.stem}.before-upgrade-{timestamp}{source_path.suffix}"
    )
    counter = 1
    while candidate.exists():
        candidate = source_path.with_name(
            f"{source_path.stem}.before-upgrade-{timestamp}-{counter}{source_path.suffix}"
        )
        counter += 1
    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(candidate)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return candidate


def upgrade_database(database_url: str, revision: str = "head") -> MigrationResult:
    previous = get_migration_status(database_url)
    if previous.is_current and revision == "head":
        return MigrationResult(previous=previous, current=previous, backup_path=None)
    if not previous.is_empty and not previous.current_revisions and not previous.inferred_revision:
        raise DatabaseRevisionError(
            "Database has tables but no recognized Alembic revision. "
            "Refusing to stamp it automatically."
        )
    backup_path = backup_sqlite_database(database_url)
    config = alembic_config(database_url)
    stamped = None
    if not previous.current_revisions and previous.inferred_revision:
        stamped = previous.inferred_revision
        command.stamp(config, stamped)
    command.upgrade(config, revision)
    current = get_migration_status(database_url)
    return MigrationResult(
        previous=previous,
        current=current,
        backup_path=backup_path,
        stamped_revision=stamped,
    )


def downgrade_database(database_url: str, revision: str) -> MigrationResult:
    previous = get_migration_status(database_url)
    if not previous.current_revisions:
        raise DatabaseRevisionError("Cannot downgrade an unversioned database")
    backup_path = backup_sqlite_database(database_url)
    command.downgrade(alembic_config(database_url), revision)
    return MigrationResult(
        previous=previous,
        current=get_migration_status(database_url),
        backup_path=backup_path,
    )


def require_current_database(database_url: str, *, engine: Engine | None = None) -> None:
    status = get_migration_status(database_url, engine=engine)
    if status.is_current:
        return
    raise DatabaseRevisionError(
        "MEAP database upgrade required: "
        f"current={status.current_label}, expected={status.head_label}. "
        "Stop the app and run: meap db upgrade"
    )
