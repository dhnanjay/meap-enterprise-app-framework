"""Notebook registry and durable audit events.

Revision ID: b82e7c341a10
Revises: fa11f6602989
Create Date: 2026-08-13

This migration creates metadata only. It does not install or execute Marimo or
Jupyter, expose routes, or create a notebook process registry.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b82e7c341a10"
down_revision: Union[str, None] = "fa11f6602989"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_notebooks",
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "engine",
            sa.Enum("MARIMO", "JUPYTER", name="notebookengine"),
            nullable=False,
        ),
        sa.Column(
            "mode",
            sa.Enum("EXTERNAL", "APPLICATION", "EDITABLE", name="notebookmode"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "ACTIVE", "DISABLED", name="notebookstatus"),
            nullable=False,
        ),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("source_path", sa.String(length=1000), nullable=True),
        sa.Column("source_checksum", sa.String(length=200), nullable=True),
        sa.Column("runtime_profile", sa.String(length=200), nullable=True),
        sa.Column("environment_lock_hash", sa.String(length=200), nullable=True),
        sa.Column("required_permission", sa.String(length=200), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("notebook_id"),
    )
    op.create_index(
        "ix_platform_notebooks_organization_id",
        "platform_notebooks",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_platform_notebooks_status",
        "platform_notebooks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_platform_notebooks_org_status",
        "platform_notebooks",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "platform_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=200), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("runtime_profile", sa.String(length=200), nullable=True),
        sa.Column("notebook_version", sa.String(length=200), nullable=True),
        sa.Column("environment_lock_hash", sa.String(length=200), nullable=True),
        sa.Column("data_snapshot_id", sa.String(length=200), nullable=True),
        sa.Column("input_artifact_ids", sa.JSON(), nullable=True),
        sa.Column("output_artifact_ids", sa.JSON(), nullable=True),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    for column in (
        "event_type",
        "occurred_at",
        "organization_id",
        "actor_user_id",
        "entity_id",
        "correlation_id",
    ):
        op.create_index(
            f"ix_platform_audit_events_{column}",
            "platform_audit_events",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "correlation_id",
        "entity_id",
        "actor_user_id",
        "organization_id",
        "occurred_at",
        "event_type",
    ):
        op.drop_index(
            f"ix_platform_audit_events_{column}",
            table_name="platform_audit_events",
        )
    op.drop_table("platform_audit_events")

    op.drop_index("ix_platform_notebooks_org_status", table_name="platform_notebooks")
    op.drop_index("ix_platform_notebooks_status", table_name="platform_notebooks")
    op.drop_index(
        "ix_platform_notebooks_organization_id", table_name="platform_notebooks"
    )
    op.drop_table("platform_notebooks")
