"""Shared test fixtures for MEAP (Section 59).

The test profile uses an in-memory SQLite database so every test starts clean.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import Iterator

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Set test environment BEFORE any app imports
os.environ.setdefault("MEAP_PROFILE", "test")
os.environ.setdefault("MEAP_AUTH_ENABLED", "false")
os.environ.setdefault("MEAP_DEVELOPER_AREA", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.platform.database.base import Base
from app.platform.database.session import init_session_factory
from app.settings import get_settings


@pytest.fixture(scope="function")
def db_engine():
    """Fresh in-memory database for each test.

    StaticPool + check_same_thread=False ensures the single in-memory DB
    is shared across threads (TestClient runs requests in a separate thread).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Iterator[Session]:
    """Database session for repository/service tests."""
    _factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = _factory()
    init_session_factory(_factory)
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_engine) -> Iterator[TestClient]:
    """FastAPI test client with a fresh in-memory database.

    We patch the engine to use the in-memory DB and trigger table creation
    through the lifespan.
    """
    import app.platform.database.base as db_base
    import app.main as main_module

    original_make_engine = db_base.make_engine
    db_base.make_engine = lambda url=None: db_engine

    # Force table creation for test
    Base.metadata.create_all(bind=db_engine)

    test_app = main_module.create_app()
    with TestClient(test_app) as c:
        yield c

    db_base.make_engine = original_make_engine