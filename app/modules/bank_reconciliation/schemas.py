"""Bank Reconciliation — Schemas / View Models (Sections 14, 30).

Templates shall not receive arbitrary database models.
Routes/services prepare explicit view models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.platform.templates.query_state import PageQuery

from app.modules.bank_reconciliation.models import (
    ExceptionStatus,
    ReconciliationStatus,
)


# ── View Models (for templates) ─────────────────────────────────────────────


@dataclass(frozen=True)
class ReconciliationSummaryVM:
    """View model for list rows."""

    reconciliation_id: str
    reference: str
    account_name: str
    period: str
    status: ReconciliationStatus
    exception_count: int
    statement_balance: Decimal
    book_balance: Decimal
    difference: Decimal
    created_at: datetime


@dataclass(frozen=True)
class ReconciliationDetailVM:
    """View model for detail page."""

    reconciliation_id: str
    reference: str
    account_name: str
    account_number: str | None
    period: str
    status: ReconciliationStatus
    statement_balance: Decimal
    book_balance: Decimal
    difference: Decimal
    exception_count: int
    exception_summary: dict[str, int]
    source_artifact_id: str | None
    job_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class ExceptionRowVM:
    """View model for exception table rows."""

    exception_id: str
    transaction_date: datetime
    description: str
    amount: Decimal
    account: str
    status: ExceptionStatus
    match_candidate: str | None


@dataclass(frozen=True)
class ReconciliationListVM:
    """Full list page view model."""

    items: list[ReconciliationSummaryVM]
    total_count: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True)
class ExceptionListVM:
    """Full exceptions page view model."""

    reconciliation: ReconciliationDetailVM
    items: list[ExceptionRowVM]
    total_count: int
    page: int
    page_size: int
    total_pages: int


# ── Query Models (URL State — Section: URL and Query-State Architecture) ────


class ReconciliationQuery(PageQuery):
    """Module-specific list filters. The URL is the canonical view state."""


class ExceptionQuery(PageQuery):
    """Exception list filters — all expressed as URL query params."""

    status: ExceptionStatus | None = None
    account: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None