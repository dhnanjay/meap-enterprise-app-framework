"""SQLAlchemy declarative base and engine factory (Sections 33, 37, 43)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all MEAP models (platform + modules)."""


def make_engine(database_url: str | None = None):
    """Create a SQLAlchemy engine from settings or override URL."""
    url = database_url or get_settings().database_url
    connect_args: dict[str, bool] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True)


def make_session_factory(engine=None) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the given engine."""
    return sessionmaker(
        bind=engine or make_engine(),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )