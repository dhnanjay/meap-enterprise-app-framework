"""MEAP host-side operator command."""

from __future__ import annotations

import argparse

from app.platform.database.cli import run_command as run_database_command


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="meap")
    areas = root.add_subparsers(dest="area", required=True)
    database = areas.add_parser("db", help="Inspect or change the database schema")
    commands = database.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show current and expected revisions")
    commands.add_parser("upgrade", help="Back up SQLite and upgrade to head")
    downgrade = commands.add_parser(
        "downgrade", help="Back up SQLite and downgrade to an explicit revision"
    )
    downgrade.add_argument("--revision", required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.area == "db":
        run_database_command(args.command, getattr(args, "revision", None))


if __name__ == "__main__":
    main()
