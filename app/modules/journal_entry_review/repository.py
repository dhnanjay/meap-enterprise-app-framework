"""Journal Entry Review — Repository (Section 28).

Repositories own persistence: database reads, writes, query composition.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.platform.templates.query_state import SortMapper

from app.modules.journal_entry_review.models import (
    JournalEntry,
    JournalEntryReview,
)
from app.modules.journal_entry_review.schemas import EntryQuery, JEReviewQuery


REVIEW_SORT = SortMapper(
    {
        "engagement": JournalEntryReview.engagement,
        "period": JournalEntryReview.period,
        "status": JournalEntryReview.status,
        "created_at": JournalEntryReview.created_at,
    }
)

ENTRY_SORT = SortMapper(
    {
        "je_number": JournalEntry.je_number,
        "amount": JournalEntry.amount,
        "posting_date": JournalEntry.posting_date,
        "risk_level": JournalEntry.risk_level,
        "account": JournalEntry.account,
    }
)


class JournalEntryReviewRepository:
    """All persistence for the journal_entry_review module."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Reviews ───────────────────────────────────────────────────────────

    def create(self, review: JournalEntryReview) -> JournalEntryReview:
        self._db.add(review)
        self._db.flush()
        return review

    def get(self, review_id: str) -> JournalEntryReview | None:
        return self._db.get(JournalEntryReview, review_id)

    def list(
        self, query: JEReviewQuery
    ) -> tuple[list[JournalEntryReview], int]:
        """Return (items, total_count) applying search, sort, pagination."""
        stmt = select(JournalEntryReview)

        if query.q:
            pattern = f"%{query.q}%"
            stmt = stmt.where(
                or_(
                    JournalEntryReview.engagement.ilike(pattern),
                    JournalEntryReview.period.ilike(pattern),
                )
            )

        if query.status:
            stmt = stmt.where(JournalEntryReview.status == query.status)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self._db.execute(count_stmt).scalar() or 0

        col = REVIEW_SORT.resolve(query.sort)
        if col is not None:
            stmt = stmt.order_by(col.desc() if query.is_desc else col.asc())
        else:
            stmt = stmt.order_by(JournalEntryReview.created_at.desc())

        stmt = stmt.offset(query.offset).limit(query.page_size)
        items = list(self._db.execute(stmt).scalars().all())
        return items, total

    def update_status(self, review_id: str, status) -> JournalEntryReview | None:
        review = self.get(review_id)
        if review:
            review.status = status
            self._db.flush()
        return review

    # ── Entries ───────────────────────────────────────────────────────────

    def create_entry(self, entry: JournalEntry) -> JournalEntry:
        self._db.add(entry)
        self._db.flush()
        return entry

    def get_entry(self, entry_id: str) -> JournalEntry | None:
        return self._db.get(JournalEntry, entry_id)

    def list_entries(
        self, review_id: str, query: EntryQuery
    ) -> tuple[list[JournalEntry], int]:
        stmt = select(JournalEntry).where(JournalEntry.review_id == review_id)

        if query.status:
            stmt = stmt.where(JournalEntry.status == query.status)
        if query.risk_level:
            stmt = stmt.where(JournalEntry.risk_level == query.risk_level)
        if query.account:
            stmt = stmt.where(JournalEntry.account.ilike(f"%{query.account}%"))
        if query.min_amount is not None:
            stmt = stmt.where(JournalEntry.amount >= query.min_amount)
        if query.q:
            stmt = stmt.where(JournalEntry.description.ilike(f"%{query.q}%"))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self._db.execute(count_stmt).scalar() or 0

        col = ENTRY_SORT.resolve(query.sort)
        if col is not None:
            stmt = stmt.order_by(col.desc() if query.is_desc else col.asc())
        else:
            stmt = stmt.order_by(JournalEntry.posting_date.desc())

        stmt = stmt.offset(query.offset).limit(query.page_size)
        items = list(self._db.execute(stmt).scalars().all())
        return items, total

    def update_entry_status(
        self, entry_id: str, status, notes: str | None = None
    ) -> JournalEntry | None:
        entry = self.get_entry(entry_id)
        if entry:
            entry.status = status
            if notes is not None:
                entry.reviewer_notes = notes
            self._db.flush()
        return entry

    def count_by_risk(self, review_id: str) -> dict[str, int]:
        stmt = (
            select(JournalEntry.risk_level, func.count())
            .where(JournalEntry.review_id == review_id)
            .group_by(JournalEntry.risk_level)
        )
        rows = self._db.execute(stmt).all()
        return {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in rows}

    def count_entries(self, review_id: str) -> int:
        stmt = select(func.count()).where(JournalEntry.review_id == review_id)
        return self._db.execute(stmt).scalar() or 0