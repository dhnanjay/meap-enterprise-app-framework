"""Durable audit-event model.

Audit events record who did what, in which organization, and with which
reproducibility context. They never contain credentials, session tokens, or
complete notebook/data payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class AuditEvent(Base):
    """Append-only record of a security- or business-significant event."""

    __tablename__ = "platform_audit_events"
    __table_args__ = (
        Index(
            "ix_platform_audit_events_org_occurred",
            "organization_id",
            "occurred_at",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    event_type: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, default="SUCCEEDED")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    # Reproducibility fields are nullable for ordinary events but mandatory by
    # policy when an executable notebook runtime is introduced later.
    runtime_profile: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notebook_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment_lock_hash: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    data_snapshot_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    output_artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditEvent {self.event_id[:8]} {self.event_type} {self.outcome}>"
