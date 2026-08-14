"""Journal Entry Review — Service (Section 27).

Services implement business use cases.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.platform.errors.taxonomy import NotFoundError, ValidationError

from app.modules.journal_entry_review.models import (
    JEReviewStatus,
    JournalEntry,
    JournalEntryReview,
    RiskLevel,
)
from app.modules.journal_entry_review.repository import JournalEntryReviewRepository
from app.modules.journal_entry_review.schemas import (
    EntryListVM,
    EntryQuery,
    EntryRowVM,
    JEReviewDetailVM,
    JEReviewListVM,
    JEReviewQuery,
    JEReviewSummaryVM,
)

logger = structlog.get_logger()


class JournalEntryReviewService:
    """Business use cases for the journal_entry_review module."""

    def __init__(self, db: Session, organization_id: str = "local-development") -> None:
        self._db = db
        self._organization_id = organization_id
        self._repo = JournalEntryReviewRepository(db, organization_id)

    # ── List reviews ─────────────────────────────────────────────────────

    def list_reviews(self, query: JEReviewQuery) -> JEReviewListVM:
        items, total = self._repo.list(query)
        total_pages = math.ceil(total / query.page_size) if total > 0 else 0

        return JEReviewListVM(
            items=[
                JEReviewSummaryVM(
                    review_id=r.review_id,
                    engagement=r.engagement,
                    period=r.period,
                    status=r.status,
                    total_entries=r.total_entries,
                    flagged_count=r.flagged_count,
                    approved_count=r.approved_count,
                    created_at=r.created_at,
                )
                for r in items
            ],
            total_count=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
        )

    # ── Get detail ───────────────────────────────────────────────────────

    def get_detail(self, review_id: str) -> JEReviewDetailVM:
        review = self._repo.get(review_id)
        if not review:
            raise NotFoundError(
                module="journal_entry_review",
                operation="get_detail",
                reason_code="REVIEW_NOT_FOUND",
                safe_message=f"JE Review {review_id} not found",
            )

        risk_summary = self._repo.count_by_risk(review_id)

        return JEReviewDetailVM(
            review_id=review.review_id,
            engagement=review.engagement,
            period=review.period,
            status=review.status,
            total_entries=review.total_entries,
            flagged_count=review.flagged_count,
            approved_count=review.approved_count,
            risk_summary=risk_summary,
            source_artifact_id=review.source_artifact_id,
            created_at=review.created_at,
        )

    # ── Create review ────────────────────────────────────────────────────

    def create_review(
        self,
        engagement: str,
        period: str,
        created_by: str | None = None,
        source_artifact_id: str | None = None,
    ) -> JEReviewDetailVM:
        if not engagement.strip():
            raise ValidationError(
                module="journal_entry_review",
                operation="create_review",
                reason_code="MISSING_ENGAGEMENT",
                safe_message="Engagement name is required",
            )

        review = JournalEntryReview(
            organization_id=self._organization_id,
            engagement=engagement,
            period=period,
            source_artifact_id=source_artifact_id,
            status=JEReviewStatus.UNREVIEWED,
            created_by=created_by,
        )
        self._repo.create(review)
        self._db.commit()

        logger.info(
            "je_review.created",
            review_id=review.review_id,
            engagement=engagement,
        )
        return self.get_detail(review.review_id)

    # ── List entries ─────────────────────────────────────────────────────

    def list_entries(
        self, review_id: str, query: EntryQuery
    ) -> EntryListVM:
        detail = self.get_detail(review_id)
        items, total = self._repo.list_entries(review_id, query)
        total_pages = math.ceil(total / query.page_size) if total > 0 else 0

        return EntryListVM(
            review=detail,
            items=[
                EntryRowVM(
                    entry_id=e.entry_id,
                    je_number=e.je_number,
                    account=e.account,
                    description=e.description,
                    amount=e.amount,
                    posting_date=e.posting_date,
                    risk_level=e.risk_level,
                    risk_factors=e.risk_factors,
                    status=e.status,
                    reviewer_notes=e.reviewer_notes,
                )
                for e in items
            ],
            total_count=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
        )

    # ── Review workflow (Section 54) ─────────────────────────────────────

    def flag_entry(self, entry_id: str, notes: str | None = None) -> EntryRowVM:
        entry = self._repo.update_entry_status(
            entry_id, JEReviewStatus.FLAGGED, notes
        )
        if not entry:
            raise NotFoundError(
                module="journal_entry_review",
                operation="flag_entry",
                reason_code="ENTRY_NOT_FOUND",
                safe_message=f"Entry {entry_id} not found",
            )
        self._db.commit()
        logger.info("je_entry.flagged", entry_id=entry_id)
        return self._entry_to_vm(entry)

    def approve_entry(self, entry_id: str, notes: str | None = None) -> EntryRowVM:
        entry = self._repo.update_entry_status(
            entry_id, JEReviewStatus.APPROVED, notes
        )
        if not entry:
            raise NotFoundError(
                module="journal_entry_review",
                operation="approve_entry",
                reason_code="ENTRY_NOT_FOUND",
                safe_message=f"Entry {entry_id} not found",
            )
        self._db.commit()
        logger.info("je_entry.approved", entry_id=entry_id)
        return self._entry_to_vm(entry)

    def reject_entry(self, entry_id: str, notes: str | None = None) -> EntryRowVM:
        entry = self._repo.update_entry_status(
            entry_id, JEReviewStatus.REJECTED, notes
        )
        if not entry:
            raise NotFoundError(
                module="journal_entry_review",
                operation="reject_entry",
                reason_code="ENTRY_NOT_FOUND",
                safe_message=f"Entry {entry_id} not found",
            )
        self._db.commit()
        logger.info("je_entry.rejected", entry_id=entry_id)
        return self._entry_to_vm(entry)

    def _entry_to_vm(self, entry: JournalEntry) -> EntryRowVM:
        return EntryRowVM(
            entry_id=entry.entry_id,
            je_number=entry.je_number,
            account=entry.account,
            description=entry.description,
            amount=entry.amount,
            posting_date=entry.posting_date,
            risk_level=entry.risk_level,
            risk_factors=entry.risk_factors,
            status=entry.status,
            reviewer_notes=entry.reviewer_notes,
        )
