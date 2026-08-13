"""Bank Reconciliation — Jobs (Section 31).

Jobs are entry points for asynchronous operations.
A job must delegate substantive business behavior to services,
not duplicate business logic.

    HTTP route → service
    Worker job → same service
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.platform.errors.taxonomy import MEAPError
from app.platform.jobs.service import JobService

from app.modules.bank_reconciliation.repository import BankReconciliationRepository
from app.modules.bank_reconciliation.models import (
    ExceptionStatus,
    ReconciliationException,
    ReconciliationStatus,
)


def ingest_workbook(
    db: Session,
    job_id: str,
    reconciliation_id: str,
    artifact_id: str,
    **kwargs: Any,
) -> None:
    """Parse an uploaded workbook and create reconciliation exceptions.

    This is the heavy-processing entry point (Section 72).
    In production this runs in a worker; in local dev, in a background task.
    """
    job_service = JobService(db)
    repo = BankReconciliationRepository(db)
    recon = repo.get(reconciliation_id)

    if not recon:
        job_service.mark_failed(
            job_id, "RECONCILIATION_NOT_FOUND", f"Reconciliation {reconciliation_id} not found"
        )
        return

    try:
        job_service.update_progress(job_id, 10.0)

        # In a real implementation, this would:
        # 1. Read the artifact from storage (artifact_id)
        # 2. Parse the workbook (pandas/polars)
        # 3. Normalize records
        # 4. Run matching logic
        # For the starter pack, we simulate with a no-op that marks success.

        job_service.update_progress(job_id, 35.0)

        # Example: update reconciliation status to IN_PROGRESS
        repo.update_status(reconciliation_id, ReconciliationStatus.IN_PROGRESS)
        db.commit()

        job_service.update_progress(job_id, 65.0)
        job_service.update_progress(job_id, 85.0)
        job_service.update_progress(job_id, 95.0)

        # Link the artifact to the reconciliation
        recon.source_artifact_id = artifact_id
        recon.job_id = job_id
        recon.status = ReconciliationStatus.MATCHED
        db.commit()

        job_service.mark_succeeded(
            job_id,
            result_meta={"reconciliation_id": reconciliation_id},
        )

    except Exception as e:
        db.rollback()
        error_code = type(e).__name__
        if isinstance(e, MEAPError):
            error_code = e.reason_code or error_code
        job_service.mark_failed(job_id, error_code, str(e))


def seed_sample_exceptions(
    db: Session,
    reconciliation_id: str,
    count: int = 5,
) -> None:
    """Utility to create sample exception data for demo purposes."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    import random

    repo = BankReconciliationRepository(db)
    descriptions = [
        "Wire transfer - unmatched",
        "Bank fee not in books",
        "Deposit in transit",
        "Outstanding check",
        "Interest credit",
        "Foreign exchange adjustment",
        "Direct debit - unauthorized",
        "Customer payment mismatch",
    ]
    accounts = ["10245 - Operating", "10246 - Payroll", "10247 - AP", "10248 - AR"]

    for i in range(count):
        exc = ReconciliationException(
            reconciliation_id=reconciliation_id,
            transaction_date=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
            description=random.choice(descriptions),
            amount=Decimal(str(random.randint(100, 50000))),
            account=random.choice(accounts),
            status=random.choice(list(ExceptionStatus)),
        )
        repo.create_exception(exc)

    db.commit()