"""Journal Entry Review — Models (Section 29).

Models contain domain vocabulary and durable business structures.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.database.base import Base


class JEReviewStatus(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    IN_REVIEW = "IN_REVIEW"
    FLAGGED = "FLAGGED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class JournalEntryReview(Base):
    __tablename__ = "je_reviews"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    engagement: Mapped[str] = mapped_column(String(200), nullable=False)
    period: Mapped[str] = mapped_column(String(50), nullable=False)
    source_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[JEReviewStatus] = mapped_column(
        SAEnum(JEReviewStatus), default=JEReviewStatus.UNREVIEWED, nullable=False
    )
    total_entries: Mapped[int] = mapped_column(default=0)
    flagged_count: Mapped[int] = mapped_column(default=0)
    approved_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    entries: Mapped[list[JournalEntry]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class JournalEntry(Base):
    __tablename__ = "je_review_entries"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("je_reviews.review_id"), nullable=False
    )
    je_number: Mapped[str] = mapped_column(String(50), nullable=False)
    account: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    posting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel), default=RiskLevel.LOW, nullable=False
    )
    risk_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JEReviewStatus] = mapped_column(
        SAEnum(JEReviewStatus), default=JEReviewStatus.UNREVIEWED, nullable=False
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    review: Mapped[JournalEntryReview] = relationship(back_populates="entries")