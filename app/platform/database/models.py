"""Platform-level database models: Job, Artifact, EvidenceItem.

These are platform concepts (Section 6) — used by substantially every application.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------
# Job model (Section 33)
# ------------------------------------------------------------------


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base):
    """Durable record for every asynchronous execution (Section 33).

    Every background operation receives a Job row so it is observable
    and traceable through correlation IDs.
    """

    __tablename__ = "platform_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    module: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    input_artifact_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_artifact_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Job {self.job_id[:8]} {self.module}.{self.operation} {self.status.value}>"


# ------------------------------------------------------------------
# Artifact model (Section 37)
# ------------------------------------------------------------------


class Artifact(Base):
    """A file or object within MEAP's artifact infrastructure (Section 37).

    An Artifact answers: What file/object exists?
    Derived artifacts preserve provenance via source_artifact_id (Section 38).
    """

    __tablename__ = "platform_artifacts"

    artifact_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size: Mapped[int] = mapped_column(default=0)
    checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_artifacts.artifact_id"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_jobs.job_id"), nullable=True
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    source: Mapped[Artifact | None] = relationship(
        "Artifact", remote_side="Artifact.artifact_id", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Artifact {self.artifact_id[:8]} {self.artifact_type} {self.filename}>"


# ------------------------------------------------------------------
# Evidence model (Section 39)
# ------------------------------------------------------------------


class EvidenceItem(Base):
    """Evidence is distinct from Artifact (Section 39).

    Artifact answers: What file/object exists?
    Evidence answers: What information supports this conclusion?

    An EvidenceItem may reference an artifact, worksheet, cell range, page,
    screenshot, transcript interval, etc.
    """

    __tablename__ = "platform_evidence"

    evidence_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_artifacts.artifact_id"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    artifact: Mapped[Artifact | None] = relationship(lazy="select")

    def __repr__(self) -> str:
        return f"<EvidenceItem {self.evidence_id[:8]} {self.evidence_type}>"