"""Local administrative commands for initializing MEAP authentication."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.auth import models as _auth_models  # noqa: F401
from app.platform.auth.models import BootstrapState, Membership
from app.platform.auth.service import AuthService
from app.platform.database.base import Base, make_engine, make_session_factory
from app.settings import get_settings


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m app.platform.auth.cli")
    commands = root.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-admin", help="Create the first administrator enrollment")
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--display-name", required=True)
    bootstrap.add_argument("--organization", required=True)
    bootstrap.add_argument("--base-url", default="http://127.0.0.1:8000")
    reissue = commands.add_parser(
        "reissue-bootstrap-enrollment",
        help="Replace an expired enrollment for an incomplete initial bootstrap",
    )
    reissue.add_argument("--base-url", default="http://127.0.0.1:8000")
    return root


def main() -> None:
    args = parser().parse_args()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    if settings.profile in {"local", "development", "test"}:
        Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        service = AuthService(db, settings)
        if args.command == "bootstrap-admin":
            result = service.bootstrap_admin(
                email=args.email,
                display_name=args.display_name,
                organization_name=args.organization,
            )
        else:
            state = db.get(BootstrapState, "initial_admin")
            if state is None or state.completed_at is not None:
                raise SystemExit("No incomplete administrator bootstrap is available")
            membership = db.scalar(
                select(Membership).where(Membership.user_id == state.administrator_user_id)
            )
            if membership is None:
                raise SystemExit("Bootstrap membership is missing")
            result = service.issue_enrollment(membership, created_by_user_id=None)
            db.commit()
        print("Open this one-time enrollment URL in a private browser window:")
        print(args.base_url.rstrip("/") + f"/auth/enroll/{result.token}")
        print(f"The link expires in {settings.enrollment_lifetime_minutes} minutes.")


if __name__ == "__main__":
    main()

