"""Bank Reconciliation — Domain Models (Section 29).

Models contain domain vocabulary and durable business structures.
Do not blindly expose persistence models to UI templates.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ReconciliationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    MATCHED = "MATCHED"
    EXCEPTION = "EXCEPTION"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"


class ExceptionStatus(str, enum.Enum):
    UNMATCHED = "UNMATCHED"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class Reconciliation(Base):
    """A bank reconciliation run for a specific account/period."""

    __tablename__ = "br_reconciliations"

    reconciliation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    reference: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2026-07"
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus), default=ReconciliationStatus.DRAFT, nullable=False
    )
    statement_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    book_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    source_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    exceptions: Mapped[list["ReconciliationException"]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Reconciliation {self.reference} {self.status.value}>"


class ReconciliationException(Base):
    """An unmatched or discrepant transaction within a reconciliation."""

    __tablename__ = "br_exceptions"

    exception_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    reconciliation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("br_reconciliations.reconciliation_id"),
        nullable=False,
        index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    account: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus), default=ExceptionStatus.UNMATCHED, nullable=False
    )
    match_candidate: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    reconciliation: Mapped[Reconciliation] = relationship(back_populates="exceptions")

    def __repr__(self) -> str:
        return f"<Exception {self.exception_id[:8]} {self.amount} {self.status.value}>"