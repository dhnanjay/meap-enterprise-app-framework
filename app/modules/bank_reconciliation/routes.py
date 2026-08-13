"""Bank Reconciliation — Routes (Section 26).

Routes own HTTP concerns only. They should be visually boring.
Routes may: read params, validate, invoke services, select response type.
Routes may NOT contain domain rules.

URL is the canonical representation of navigable view state:
    /bank-recon/BR-2026-004/exceptions?status=unmatched&sort=amount&direction=desc&page=3
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.platform.auth.context import UserContext, get_current_user
from app.platform.database.session import get_db
from app.platform.permissions.dependencies import require_permission
from app.platform.templates.rendering import render_fragment, render_page

from app.modules.bank_reconciliation.permissions import (
    BANK_RECON_CREATE,
    BANK_RECON_ESCALATE,
    BANK_RECON_RESOLVE,
    BANK_RECON_VIEW,
)
from app.modules.bank_reconciliation.schemas import (
    ExceptionQuery,
    ReconciliationQuery,
)
from app.modules.bank_reconciliation.service import BankReconciliationService

router = APIRouter(prefix="/bank-recon", tags=["Bank Reconciliation"])


# ── List (Section: Search/Filter/Pagination as URL state) ───────────────────


@router.get("", name="br.list")
async def list_reconciliations(
    request: Request,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str | None = None,
    direction: str = "asc",
    db: Session = Depends(get_db),
):
    """List reconciliations. All view state is in the URL."""
    query = ReconciliationQuery(q=q, page=page, page_size=page_size, sort=sort, direction=direction)
    service = BankReconciliationService(db)
    vm = service.list_reconciliations(query)

    return render_page(
        request,
        "bank_reconciliation/list.html",
        {"vm": vm, "query": query},
    )


# ── Upload form ─────────────────────────────────────────────────────────────


@router.get("/upload", name="br.upload")
async def upload_form(request: Request):
    """Show the create reconciliation form."""
    return render_page(request, "bank_reconciliation/upload.html", {})


# ── Create ──────────────────────────────────────────────────────────────────


@router.post("", name="br.create")
async def create_reconciliation(
    request: Request,
    reference: str = Form(...),
    account_name: str = Form(...),
    account_number: str | None = Form(None),
    period: str = Form(...),
    statement_balance: float = Form(0),
    book_balance: float = Form(0),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(BANK_RECON_CREATE)),
):
    """Create a new reconciliation. Returns the detail fragment."""
    service = BankReconciliationService(db)
    vm = service.create_reconciliation(
        reference=reference,
        account_name=account_name,
        account_number=account_number,
        period=period,
        statement_balance=statement_balance,
        book_balance=book_balance,
        created_by=user.user_id,
    )
    return render_page(
        request,
        "bank_reconciliation/detail.html",
        {"vm": vm},
    )


# ── Detail ──────────────────────────────────────────────────────────────────


@router.get("/{reconciliation_id}", name="br.detail")
async def detail(
    request: Request,
    reconciliation_id: str,
    db: Session = Depends(get_db),
):
    """Reconciliation detail — the workspace landing page."""
    service = BankReconciliationService(db)
    vm = service.get_detail(reconciliation_id)

    return render_page(
        request,
        "bank_reconciliation/detail.html",
        {"vm": vm},
    )


# ── Exceptions (Section: Filtering + Sorting + Pagination in URL) ───────────


@router.get("/{reconciliation_id}/exceptions", name="br.exceptions")
async def exceptions(
    request: Request,
    reconciliation_id: str,
    q: str | None = None,
    status: str | None = None,
    account: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str | None = None,
    direction: str = "asc",
    db: Session = Depends(get_db),
):
    """List exceptions for a reconciliation. Entire view = URL state."""
    query = ExceptionQuery(
        q=q,
        status=status,
        account=account,
        min_amount=min_amount,
        max_amount=max_amount,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )
    service = BankReconciliationService(db)
    vm = service.list_exceptions(reconciliation_id, query)

    return render_page(
        request,
        "bank_reconciliation/exceptions.html",
        {"vm": vm, "query": query},
    )


# ── Exception actions (Review workflow — Section 54) ────────────────────────


@router.post("/exceptions/{exception_id}/resolve", name="br.resolve")
async def resolve_exception(
    request: Request,
    exception_id: str,
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(BANK_RECON_RESOLVE)),
):
    """Resolve an exception. Returns the updated row fragment."""
    service = BankReconciliationService(db)
    vm = service.resolve_exception(exception_id, user.user_id, notes)

    return render_fragment(
        request,
        "bank_reconciliation/fragments/exception_row.html",
        {"row": vm},
    )


@router.post("/exceptions/{exception_id}/escalate", name="br.escalate")
async def escalate_exception(
    request: Request,
    exception_id: str,
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: UserContext = Depends(get_current_user),
    _perm=Depends(require_permission(BANK_RECON_ESCALATE)),
):
    """Escalate an exception. Returns the updated row fragment."""
    service = BankReconciliationService(db)
    vm = service.escalate_exception(exception_id, user.user_id, notes)

    return render_fragment(
        request,
        "bank_reconciliation/fragments/exception_row.html",
        {"row": vm},
    )