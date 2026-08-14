"""Administrator-only HTML routes for workspace audit evidence."""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.platform.audit.query import AuditFilters, AuditQueryService
from app.platform.auth.context import UserContext
from app.platform.database.session import get_db
from app.platform.errors.taxonomy import NotFoundError
from app.platform.permissions.dependencies import require_workspace_admin
from app.platform.templates.rendering import render_page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", name="audit.list")
def audit_list(
    request: Request,
    q: str | None = None,
    event_type: str | None = None,
    outcome: str | None = None,
    actor_user_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_workspace_admin),
):
    selected_page_size = page_size if page_size in {25, 50, 100} else 50
    filters = AuditFilters(
        q=q.strip() if q and q.strip() else None,
        event_type=event_type or None,
        outcome=outcome or None,
        actor_user_id=actor_user_id or None,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=selected_page_size,
    )
    result = AuditQueryService(db, user.organization_id or "").list_events(filters)
    return render_page(
        request,
        "audit/list.html",
        {"result": result, "filters": filters},
    )


@router.get("/{event_id}", name="audit.detail")
def audit_detail(
    request: Request,
    event_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_workspace_admin),
):
    row = AuditQueryService(db, user.organization_id or "").get_event(event_id)
    if row is None:
        raise NotFoundError(
            module="platform",
            operation="audit_detail",
            reason_code="AUDIT_EVENT_NOT_FOUND",
            safe_message="Audit event not found",
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    return render_page(
        request,
        "audit/detail.html",
        {
            "row": row,
            "event_data_json": json.dumps(row.event.event_data or {}, indent=2, sort_keys=True),
        },
    )
