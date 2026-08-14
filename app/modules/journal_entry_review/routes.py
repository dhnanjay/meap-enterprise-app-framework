"""Journal Entry Review — Routes (Section 26).

Routes own HTTP concerns only. URL is the canonical view state:
    /je-review/JR-2026-001/entries?risk_level=HIGH&sort=amount&direction=desc&page=2
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.platform.auth.context import UserContext, get_current_user
from app.platform.database.session import get_db
from app.platform.permissions.dependencies import require_permission
from app.platform.templates.rendering import render_fragment, render_page

from app.modules.journal_entry_review.permissions import (
    JE_REVIEW_APPROVE,
    JE_REVIEW_CREATE,
    JE_REVIEW_FLAG,
    JE_REVIEW_REJECT,
    JE_REVIEW_VIEW,
)
from app.modules.journal_entry_review.schemas import EntryQuery, JEReviewQuery
from app.modules.journal_entry_review.service import JournalEntryReviewService

router = APIRouter(prefix="/je-review", tags=["Journal Entry Review"])


# ── List (Section: Search/Filter/Pagination as URL state) ───────────────────


@router.get("", name="je.list")
async def list_reviews(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str | None = None,
    direction: str = "asc",
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_VIEW)),
):
    """List JE reviews. All view state is in the URL."""
    query = JEReviewQuery(
        q=q, status=status, page=page, page_size=page_size, sort=sort, direction=direction
    )
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.list_reviews(query)

    return render_page(
        request,
        "journal_entry_review/list.html",
        {"vm": vm, "query": query},
    )


# ── New review form ─────────────────────────────────────────────────────────


@router.get("/new", name="je.new")
async def new_review_form(
    request: Request,
    _perm=Depends(require_permission(JE_REVIEW_CREATE)),
):
    """Show the create form. Uses semantic HTML per Section 21."""
    return render_page(
        request,
        "journal_entry_review/new.html",
        {},
    )


# ── Create ──────────────────────────────────────────────────────────────────


@router.post("", name="je.create")
async def create_review(
    request: Request,
    engagement: str = Form(...),
    period: str = Form(...),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_CREATE)),
):
    """Create a new JE review."""
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.create_review(
        engagement=engagement,
        period=period,
        created_by=user.user_id,
    )
    return render_page(
        request,
        "journal_entry_review/detail.html",
        {"vm": vm},
    )


# ── Detail ──────────────────────────────────────────────────────────────────


@router.get("/{review_id}", name="je.detail")
async def detail(
    request: Request,
    review_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_VIEW)),
):
    """JE review detail — workspace landing page."""
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.get_detail(review_id)

    return render_page(
        request,
        "journal_entry_review/detail.html",
        {"vm": vm},
    )


# ── Entries (Section: Filtering + Sorting + Pagination in URL) ──────────────


@router.get("/{review_id}/entries", name="je.entries")
async def entries(
    request: Request,
    review_id: str,
    q: str | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    account: str | None = None,
    min_amount: float | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str | None = None,
    direction: str = "asc",
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_VIEW)),
):
    """List entries for a review. Entire view = URL state."""
    query = EntryQuery(
        q=q,
        status=status,
        risk_level=risk_level,
        account=account,
        min_amount=min_amount,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.list_entries(review_id, query)

    return render_page(
        request,
        "journal_entry_review/entries.html",
        {"vm": vm, "query": query},
    )


# ── Entry actions (Review workflow — Section 54) ────────────────────────────


@router.post("/entries/{entry_id}/flag", name="je.flag")
async def flag_entry(
    request: Request,
    entry_id: str,
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_FLAG)),
):
    """Flag an entry. Returns the updated row fragment."""
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.flag_entry(entry_id, notes)

    return render_fragment(
        request,
        "journal_entry_review/fragments/entry_row.html",
        {"row": vm},
    )


@router.post("/entries/{entry_id}/approve", name="je.approve")
async def approve_entry(
    request: Request,
    entry_id: str,
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_APPROVE)),
):
    """Approve an entry. Returns the updated row fragment."""
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.approve_entry(entry_id, notes)

    return render_fragment(
        request,
        "journal_entry_review/fragments/entry_row.html",
        {"row": vm},
    )


@router.post("/entries/{entry_id}/reject", name="je.reject")
async def reject_entry(
    request: Request,
    entry_id: str,
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(JE_REVIEW_REJECT)),
):
    """Reject an entry. Returns the updated row fragment."""
    service = JournalEntryReviewService(db, user.organization_id or "local-development")
    vm = service.reject_entry(entry_id, notes)

    return render_fragment(
        request,
        "journal_entry_review/fragments/entry_row.html",
        {"row": vm},
    )
