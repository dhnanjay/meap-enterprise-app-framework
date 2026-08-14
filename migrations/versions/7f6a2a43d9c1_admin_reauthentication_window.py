"""administrator reauthentication window

Revision ID: 7f6a2a43d9c1
Revises: 3836580891fe
Create Date: 2026-08-13 20:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f6a2a43d9c1"
down_revision: Union[str, None] = "3836580891fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "reauthenticated_at")
