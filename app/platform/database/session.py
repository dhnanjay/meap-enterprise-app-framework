"""Database session dependency for FastAPI routes."""

from __future__ import annotations

from collections.abc import Generator
from typing import AsyncGenerator

from sqlalchemy.orm import Session, sessionmaker

from app.platform.database.base import make_session_factory

_session_factory: sessionmaker[Session] | None = None


def init_session_factory(factory: sessionmaker[Session]) -> None:
    """Set the global session factory (called at startup)."""
    global _session_factory
    _session_factory = factory


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        init_session_factory(make_session_factory())
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a database session (Section 28).

    Routes and services consume this — never instantiate sessions ad hoc.
    """
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()