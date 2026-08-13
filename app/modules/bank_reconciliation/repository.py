"""Bank Reconciliation — Repository (Section 28).

Repositories own persistence: database reads, writes, query composition.
They shall not render HTML, contain HTTP semantics, or decide accounting policy.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.platform.templates.query_state import SortMapper

from app.modules.bank_reconciliation.models import (
    ExceptionStatus,
    Reconciliation,
    ReconciliationException,
    ReconciliationStatus,
)
from app.modules.bank_reconciliation.schemas import (
    ExceptionQuery,
    ReconciliationQuery,
)


# Allowed sort columns — never interpolate raw request data into SQL.
RECON_SORT = SortMapper(
    {
        "reference": Reconciliation.reference,
        "account": Reconciliation.account_name,
        "period": Reconciliation.period,
        "status": Reconciliation.status,
        "created_at": Reconciliation.created_at,
    }
)

EXCEPTION_SORT = SortMapper(
    {
        "date": ReconciliationException.transaction_date,
        "description": ReconciliationException.description,
        "amount": ReconciliationException.amount,
        "account": ReconciliationException.account,
        "status": ReconciliationException.status,
    }
)


class BankReconciliationRepository:
    """All persistence for the bank_reconciliation module."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Reconciliations ──────────────────────────────────────────────────

    def create(self, recon: Reconciliation) -> Reconciliation:
        self._db.add(recon)
        self._db.flush()
        return recon

    def get(self, reconciliation_id: str) -> Reconciliation | None:
        return self._db.get(Reconciliation, reconciliation_id)

    def get_by_reference(self, reference: str) -> Reconciliation | None:
        stmt = select(Reconciliation).where(Reconciliation.reference == reference)
        return self._db.execute(stmt).scalar_one_or_none()

    def list(
        self, query: ReconciliationQuery
    ) -> tuple[list[Reconciliation], int]:
        """Return (items, total_count) applying search, sort, pagination."""
        stmt = select(Reconciliation)

        if query.q:
            pattern = f"%{query.q}%"
            stmt = stmt.where(
                or_(
                    Reconciliation.reference.ilike(pattern),
                    Reconciliation.account_name.ilike(pattern),
                    Reconciliation.period.ilike(pattern),
                )
            )

        # Count
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self._db.execute(count_stmt).scalar() or 0

        # Sort
        col = RECON_SORT.resolve(query.sort)
        if col is not None:
            stmt = stmt.order_by(col.desc() if query.is_desc else col.asc())
        else:
            stmt = stmt.order_by(Reconciliation.created_at.desc())

        # Paginate
        stmt = stmt.offset(query.offset).limit(query.page_size)
        items = list(self._db.execute(stmt).scalars().all())
        return items, total

    def update_status(
        self, reconciliation_id: str, status: ReconciliationStatus
    ) -> Reconciliation | None:
        recon = self.get(reconciliation_id)
        if recon:
            recon.status = status
            self._db.flush()
        return recon

    # ── Exceptions ───────────────────────────────────────────────────────

    def create_exception(self, exc: ReconciliationException) -> ReconciliationException:
        self._db.add(exc)
        self._db.flush()
        return exc

    def get_exception(self, exception_id: str) -> ReconciliationException | None:
        return self._db.get(ReconciliationException, exception_id)

    def list_exceptions(
        self, reconciliation_id: str, query: ExceptionQuery
    ) -> tuple[list[ReconciliationException], int]:
        stmt = select(ReconciliationException).where(
            ReconciliationException.reconciliation_id == reconciliation_id
        )

        if query.status:
            stmt = stmt.where(ReconciliationException.status == query.status)
        if query.account:
            stmt = stmt.where(
                ReconciliationException.account.ilike(f"%{query.account}%")
            )
        if query.min_amount is not None:
            stmt = stmt.where(ReconciliationException.amount >= query.min_amount)
        if query.max_amount is not None:
            stmt = stmt.where(ReconciliationException.amount <= query.max_amount)
        if query.q:
            pattern = f"%{query.q}%"
            stmt = stmt.where(ReconciliationException.description.ilike(pattern))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self._db.execute(count_stmt).scalar() or 0

        col = EXCEPTION_SORT.resolve(query.sort)
        if col is not None:
            stmt = stmt.order_by(col.desc() if query.is_desc else col.asc())
        else:
            stmt = stmt.order_by(ReconciliationException.transaction_date.desc())

        stmt = stmt.offset(query.offset).limit(query.page_size)
        items = list(self._db.execute(stmt).scalars().all())
        return items, total

    def update_exception_status(
        self,
        exception_id: str,
        status: ExceptionStatus,
        resolved_by: str | None = None,
        notes: str | None = None,
    ) -> ReconciliationException | None:
        exc = self.get_exception(exception_id)
        if exc:
            exc.status = status
            if status in (ExceptionStatus.RESOLVED, ExceptionStatus.ESCALATED):
                from datetime import datetime, timezone

                exc.resolved_at = datetime.now(timezone.utc)
                exc.resolved_by = resolved_by
            if notes is not None:
                exc.notes = notes
            self._db.flush()
        return exc

    def exception_counts_by_status(
        self, reconciliation_id: str
    ) -> dict[str, int]:
        stmt = (
            select(ReconciliationException.status, func.count())
            .where(ReconciliationException.reconciliation_id == reconciliation_id)
            .group_by(ReconciliationException.status)
        )
        rows = self._db.execute(stmt).all()
        return {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in rows}

    def count_exceptions(self, reconciliation_id: str) -> int:
        stmt = select(func.count()).where(
            ReconciliationException.reconciliation_id == reconciliation_id
        )
        return self._db.execute(stmt).scalar() or 0