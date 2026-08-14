"""Host-side database lifecycle commands."""

from __future__ import annotations

import argparse

from app.platform.database.migrations import (
    DatabaseRevisionError,
    downgrade_database,
    get_migration_status,
    upgrade_database,
)
from app.settings import get_settings


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m app.platform.database.cli")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show current and expected database revisions")
    commands.add_parser(
        "upgrade", help="Back up SQLite and upgrade the configured database to head"
    )
    downgrade = commands.add_parser(
        "downgrade", help="Back up SQLite and downgrade to an explicit revision"
    )
    downgrade.add_argument("--revision", required=True)
    return root


def _show_result(result) -> None:
    if result.backup_path:
        print(f"Backup created: {result.backup_path}")
    if result.stamped_revision:
        print(f"Recognized legacy schema and stamped: {result.stamped_revision}")
    print(f"Previous revision: {result.previous.current_label}")
    print(f"Current revision: {result.current.current_label}")
    print(f"Expected head: {result.current.head_label}")


def run_command(command_name: str, revision: str | None = None) -> None:
    database_url = get_settings().database_url
    try:
        if command_name == "status":
            status = get_migration_status(database_url)
            print(f"Current revision: {status.current_label}")
            print(f"Expected head: {status.head_label}")
            print(f"Status: {'current' if status.is_current else 'upgrade required'}")
            return
        if command_name == "upgrade":
            _show_result(upgrade_database(database_url))
            return
        if not revision:
            raise SystemExit("Downgrade requires --revision")
        _show_result(downgrade_database(database_url, revision))
    except DatabaseRevisionError as exc:
        raise SystemExit(str(exc)) from exc


def main() -> None:
    args = parser().parse_args()
    run_command(args.command, getattr(args, "revision", None))


if __name__ == "__main__":
    main()
