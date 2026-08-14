"""Bank Reconciliation — Service (Section 27).

Services implement business use cases.
When a developer asks: "What actually happens when the user presses Run?"
    → service.py is the first place to inspect.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.platform.errors.taxonomy import NotFoundError, ValidationError

from app.modules.bank_reconciliation.models import (
    ExceptionStatus,
    Reconciliation,
    ReconciliationException,
    ReconciliationStatus,
)
from app.modules.bank_reconciliation.repository import BankReconciliationRepository
from app.modules.bank_reconciliation.schemas import (
    ExceptionListVM,
    ExceptionQuery,
    ExceptionRowVM,
    ReconciliationDetailVM,
    ReconciliationListVM,
    ReconciliationQuery,
    ReconciliationSummaryVM,
)

logger = structlog.get_logger()


class BankReconciliationService:
    """Business use cases for the bank_reconciliation module."""

    def __init__(self, db: Session, organization_id: str = "local-development") -> None:
        self._db = db
        self._organization_id = organization_id
        self._repo = BankReconciliationRepository(db, organization_id)

    # ── List reconciliations ─────────────────────────────────────────────

    def list_reconciliations(self, query: ReconciliationQuery) -> ReconciliationListVM:
        items, total = self._repo.list(query)
        total_pages = math.ceil(total / query.page_size) if total > 0 else 0

        return ReconciliationListVM(
            items=[
                ReconciliationSummaryVM(
                    reconciliation_id=r.reconciliation_id,
                    reference=r.reference,
                    account_name=r.account_name,
                    period=r.period,
                    status=r.status,
                    exception_count=self._repo.count_exceptions(r.reconciliation_id),
                    statement_balance=r.statement_balance,
                    book_balance=r.book_balance,
                    difference=r.statement_balance - r.book_balance,
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

    def get_detail(self, reconciliation_id: str) -> ReconciliationDetailVM:
        recon = self._repo.get(reconciliation_id)
        if not recon:
            raise NotFoundError(
                module="bank_reconciliation",
                operation="get_detail",
                reason_code="RECONCILIATION_NOT_FOUND",
                safe_message=f"Reconciliation {reconciliation_id} not found",
            )

        counts = self._repo.exception_counts_by_status(reconciliation_id)
        total_exceptions = sum(counts.values())

        return ReconciliationDetailVM(
            reconciliation_id=recon.reconciliation_id,
            reference=recon.reference,
            account_name=recon.account_name,
            account_number=recon.account_number,
            period=recon.period,
            status=recon.status,
            statement_balance=recon.statement_balance,
            book_balance=recon.book_balance,
            difference=recon.statement_balance - recon.book_balance,
            exception_count=total_exceptions,
            exception_summary=counts,
            source_artifact_id=recon.source_artifact_id,
            job_id=recon.job_id,
            created_at=recon.created_at,
        )

    # ── Create reconciliation ────────────────────────────────────────────

    def create_reconciliation(
        self,
        reference: str,
        account_name: str,
        period: str,
        statement_balance: float = 0,
        book_balance: float = 0,
        account_number: str | None = None,
        created_by: str | None = None,
    ) -> ReconciliationDetailVM:
        if self._repo.get_by_reference(reference):
            raise ValidationError(
                module="bank_reconciliation",
                operation="create_reconciliation",
                reason_code="DUPLICATE_REFERENCE",
                safe_message=f"Reference {reference} already exists",
            )

        recon = Reconciliation(
            organization_id=self._organization_id,
            reference=reference,
            account_name=account_name,
            account_number=account_number,
            period=period,
            statement_balance=statement_balance,
            book_balance=book_balance,
            status=ReconciliationStatus.DRAFT,
            created_by=created_by,
        )
        self._repo.create(recon)
        self._db.commit()

        logger.info(
            "reconciliation.created",
            reconciliation_id=recon.reconciliation_id,
            reference=reference,
        )
        return self.get_detail(recon.reconciliation_id)

    # ── List exceptions ──────────────────────────────────────────────────

    def list_exceptions(
        self, reconciliation_id: str, query: ExceptionQuery
    ) -> ExceptionListVM:
        detail = self.get_detail(reconciliation_id)  # raises NotFoundError if missing
        items, total = self._repo.list_exceptions(reconciliation_id, query)
        total_pages = math.ceil(total / query.page_size) if total > 0 else 0

        return ExceptionListVM(
            reconciliation=detail,
            items=[
                ExceptionRowVM(
                    exception_id=e.exception_id,
                    transaction_date=e.transaction_date,
                    description=e.description,
                    amount=e.amount,
                    account=e.account,
                    status=e.status,
                    match_candidate=e.match_candidate,
                )
                for e in items
            ],
            total_count=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
        )

    # ── Review workflow (Section 54) ─────────────────────────────────────

    def resolve_exception(
        self,
        exception_id: str,
        resolved_by: str,
        notes: str | None = None,
    ) -> ExceptionRowVM:
        exc = self._repo.update_exception_status(
            exception_id, ExceptionStatus.RESOLVED, resolved_by, notes
        )
        if not exc:
            raise NotFoundError(
                module="bank_reconciliation",
                operation="resolve_exception",
                reason_code="EXCEPTION_NOT_FOUND",
                safe_message=f"Exception {exception_id} not found",
            )
        self._db.commit()

        logger.info(
            "exception.resolved",
            exception_id=exception_id,
            resolved_by=resolved_by,
        )

        return ExceptionRowVM(
            exception_id=exc.exception_id,
            transaction_date=exc.transaction_date,
            description=exc.description,
            amount=exc.amount,
            account=exc.account,
            status=exc.status,
            match_candidate=exc.match_candidate,
        )

    def escalate_exception(
        self,
        exception_id: str,
        user: str,
        notes: str | None = None,
    ) -> ExceptionRowVM:
        exc = self._repo.update_exception_status(
            exception_id, ExceptionStatus.ESCALATED, user, notes
        )
        if not exc:
            raise NotFoundError(
                module="bank_reconciliation",
                operation="escalate_exception",
                reason_code="EXCEPTION_NOT_FOUND",
                safe_message=f"Exception {exception_id} not found",
            )
        self._db.commit()

        logger.info(
            "exception.escalated",
            exception_id=exception_id,
            user=user,
        )

        return ExceptionRowVM(
            exception_id=exc.exception_id,
            transaction_date=exc.transaction_date,
            description=exc.description,
            amount=exc.amount,
            account=exc.account,
            status=exc.status,
            match_candidate=exc.match_candidate,
        )
