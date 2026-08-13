"""Typed notebook registry model.

The registry records intent and policy only. It does not execute notebooks.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base
from app.platform.notebooks.permissions import NOTEBOOK_VIEW


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class NotebookEngine(str, enum.Enum):
    MARIMO = "MARIMO"
    JUPYTER = "JUPYTER"


class NotebookMode(str, enum.Enum):
    EXTERNAL = "EXTERNAL"
    APPLICATION = "APPLICATION"
    EDITABLE = "EDITABLE"


class NotebookStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class NotebookDefinition(Base):
    """A registered notebook or external notebook destination."""

    __tablename__ = "platform_notebooks"
    __table_args__ = (
        Index("ix_platform_notebooks_org_status", "organization_id", "status"),
    )

    notebook_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    engine: Mapped[NotebookEngine] = mapped_column(
        Enum(NotebookEngine, name="notebookengine"), nullable=False
    )
    mode: Mapped[NotebookMode] = mapped_column(
        Enum(NotebookMode, name="notebookmode"), nullable=False
    )
    status: Mapped[NotebookStatus] = mapped_column(
        Enum(NotebookStatus, name="notebookstatus"),
        nullable=False,
        default=NotebookStatus.DRAFT,
        index=True,
    )
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    runtime_profile: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment_lock_hash: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    required_permission: Mapped[str] = mapped_column(
        String(200), nullable=False, default=NOTEBOOK_VIEW
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    @property
    def has_reproducible_runtime(self) -> bool:
        """Whether the registry contains the minimum runtime provenance."""
        return bool(
            self.source_checksum
            and self.runtime_profile
            and self.environment_lock_hash
        )

    def __repr__(self) -> str:
        return f"<NotebookDefinition {self.notebook_id[:8]} {self.engine.value} {self.mode.value}>"
