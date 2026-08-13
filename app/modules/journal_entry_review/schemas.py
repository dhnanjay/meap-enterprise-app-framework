"""Journal Entry Review — Schemas / View Models (Sections 14, 30).

Templates shall not receive arbitrary database models.
Routes/services prepare explicit view models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.platform.templates.query_state import PageQuery

from app.modules.journal_entry_review.models import JEReviewStatus, RiskLevel


# ── View Models (for templates) ─────────────────────────────────────────────


@dataclass(frozen=True)
class JEReviewSummaryVM:
    """View model for list rows."""

    review_id: str
    engagement: str
    period: str
    status: JEReviewStatus
    total_entries: int
    flagged_count: int
    approved_count: int
    created_at: datetime


@dataclass(frozen=True)
class JEReviewDetailVM:
    """View model for detail page."""

    review_id: str
    engagement: str
    period: str
    status: JEReviewStatus
    total_entries: int
    flagged_count: int
    approved_count: int
    risk_summary: dict[str, int]
    source_artifact_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class EntryRowVM:
    """View model for entry table rows."""

    entry_id: str
    je_number: str
    account: str
    description: str
    amount: Decimal
    posting_date: datetime
    risk_level: RiskLevel
    risk_factors: str | None
    status: JEReviewStatus
    reviewer_notes: str | None


@dataclass(frozen=True)
class JEReviewListVM:
    """Full list page view model."""

    items: list[JEReviewSummaryVM]
    total_count: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True)
class EntryListVM:
    """Full entry list page view model."""

    review: JEReviewDetailVM
    items: list[EntryRowVM]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class JEReviewQuery(PageQuery):
    """Query params for listing JE reviews — URL is the state."""

    status: JEReviewStatus | None = None
    engagement: str | None = None


class EntryQuery(PageQuery):
    """Query params for listing entries within a review."""

    status: JEReviewStatus | None = None
    risk_level: RiskLevel | None = None
    account: str | None = None
    min_amount: Decimal | None = None


# Allowed sort columns (Section: Security rule for sorting)
EntrySort = Literal["je_number", "amount", "posting_date", "risk_level", "account"]
ReviewSort = Literal["engagement", "period", "status", "created_at"]