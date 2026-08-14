"""Index workspace audit timeline.

Revision ID: cc34e1a6f942
Revises: 7f6a2a43d9c1
"""

from typing import Sequence, Union

from alembic import op


revision: str = "cc34e1a6f942"
down_revision: Union[str, None] = "7f6a2a43d9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_platform_audit_events_org_occurred",
        "platform_audit_events",
        ["organization_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_audit_events_org_occurred",
        table_name="platform_audit_events",
    )
