"""Alembic migration environment for MEAP.

Reads the database URL from MEAP settings and imports all models
so autogenerate can detect them.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import settings and Base so all models are registered
from app.settings import get_settings
from app.platform.database.base import Base

# Import ALL model modules so SQLAlchemy registers them on Base.metadata.
# Platform models:
from app.platform.database import models as _platform_models  # noqa: F401
from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.notebooks import models as _notebook_models  # noqa: F401
from app.platform.auth import models as _auth_models  # noqa: F401

# Module models:
from app.modules.bank_reconciliation import models as _br_models  # noqa: F401
from app.modules.journal_entry_review import models as _je_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from MEAP settings
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to DB and apply)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
