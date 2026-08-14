"""Database migration lifecycle and safety tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.platform.database.migrations import (
    DatabaseRevisionError,
    downgrade_database,
    get_migration_status,
    require_current_database,
    upgrade_database,
)
from app.settings import Settings


PRIOR_AUTH_REVISION = "4bd8a81af4b4"


def sqlite_url(path) -> str:
    return f"sqlite:///{path}"


def test_meap_command_exposes_database_lifecycle_subcommands():
    from app.cli import parser

    assert parser().parse_args(["db", "status"]).command == "status"
    assert parser().parse_args(["db", "upgrade"]).command == "upgrade"
    downgrade = parser().parse_args(
        ["db", "downgrade", "--revision", PRIOR_AUTH_REVISION]
    )
    assert downgrade.command == "downgrade"
    assert downgrade.revision == PRIOR_AUTH_REVISION


def test_fresh_database_upgrades_to_head(tmp_path):
    database_path = tmp_path / "fresh.db"
    database_url = sqlite_url(database_path)

    before = get_migration_status(database_url)
    assert before.is_empty
    assert not before.is_current
    assert not database_path.exists(), "status must remain read-only"

    result = upgrade_database(database_url)

    assert result.backup_path is None
    assert result.current.is_current
    require_current_database(database_url)


def test_upgrade_and_downgrade_create_recoverable_sqlite_backups(tmp_path):
    database_path = tmp_path / "reversible.db"
    database_url = sqlite_url(database_path)
    upgrade_database(database_url)

    downgraded = downgrade_database(database_url, PRIOR_AUTH_REVISION)
    assert downgraded.backup_path is not None
    assert downgraded.backup_path.exists()
    assert downgraded.current.current_revisions == (PRIOR_AUTH_REVISION,)

    try:
        require_current_database(database_url)
    except DatabaseRevisionError as exc:
        assert "upgrade required" in str(exc).lower()
    else:
        raise AssertionError("A behind database must fail startup validation")

    upgraded = upgrade_database(database_url)
    assert upgraded.backup_path is not None
    assert upgraded.backup_path.exists()
    assert upgraded.current.is_current


def test_recognized_unversioned_legacy_database_is_stamped_and_preserved(tmp_path):
    database_url = sqlite_url(tmp_path / "legacy.db")
    upgrade_database(database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        organization_id = connection.execute(
            text("SELECT organization_id FROM auth_organizations LIMIT 1")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO br_reconciliations "
                "(reconciliation_id, organization_id, reference, account_name, period, status, "
                "statement_balance, book_balance, created_at) VALUES "
                "('legacy-record', :organization_id, 'LEGACY-001', 'Legacy Cash', '2026-08', "
                "'DRAFT', 100, 100, CURRENT_TIMESTAMP)"
            ),
            {"organization_id": organization_id},
        )
    engine.dispose()

    downgrade_database(database_url, PRIOR_AUTH_REVISION)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
    engine.dispose()

    legacy = get_migration_status(database_url)
    assert legacy.current_revisions == ()
    assert legacy.inferred_revision == PRIOR_AUTH_REVISION

    upgraded = upgrade_database(database_url)
    assert upgraded.stamped_revision == PRIOR_AUTH_REVISION
    assert upgraded.current.is_current
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT organization_id FROM br_reconciliations "
                "WHERE reconciliation_id = 'legacy-record'"
            )
        ).scalar_one()
    engine.dispose()


def test_unknown_unversioned_schema_is_never_stamped_automatically(tmp_path):
    database_url = sqlite_url(tmp_path / "unknown.db")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated_data (id INTEGER PRIMARY KEY)"))
    engine.dispose()

    try:
        upgrade_database(database_url)
    except DatabaseRevisionError as exc:
        assert "refusing to stamp" in str(exc).lower()
    else:
        raise AssertionError("An unknown schema must never be stamped automatically")


def test_application_startup_rejects_a_database_behind_head(tmp_path, monkeypatch):
    import app.main as main_module

    database_url = sqlite_url(tmp_path / "behind.db")
    upgrade_database(database_url)
    downgrade_database(database_url, PRIOR_AUTH_REVISION)
    settings = Settings(
        profile="local",
        auth_enabled=False,
        database_url=database_url,
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    application = main_module.create_app()

    with pytest.raises(DatabaseRevisionError, match="upgrade required"):
        with TestClient(application):
            pass
