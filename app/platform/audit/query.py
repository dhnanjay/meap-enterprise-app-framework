"""Workspace-scoped read model for the administrator audit center."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.platform.audit.models import AuditEvent
from app.platform.auth.models import User


@dataclass(frozen=True)
class AuditFilters:
    q: str | None = None
    event_type: str | None = None
    outcome: str | None = None
    actor_user_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True)
class AuditRow:
    event: AuditEvent
    actor_name: str | None
    actor_email: str | None


@dataclass(frozen=True)
class AuditListResult:
    items: tuple[AuditRow, ...]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    event_types: tuple[str, ...]
    outcomes: tuple[str, ...]
    actors: tuple[tuple[str, str], ...]


class AuditQueryService:
    """Read append-only audit records without exposing mutation methods."""

    def __init__(self, db: Session, organization_id: str) -> None:
        self.db = db
        self.organization_id = organization_id

    def _conditions(self, filters: AuditFilters) -> list:
        conditions = [AuditEvent.organization_id == self.organization_id]
        if filters.q:
            term = f"%{filters.q.strip()}%"
            conditions.append(
                or_(
                    AuditEvent.event_type.ilike(term),
                    AuditEvent.correlation_id.ilike(term),
                    AuditEvent.entity_id.ilike(term),
                    AuditEvent.actor_user_id.ilike(term),
                    User.display_name.ilike(term),
                    User.email.ilike(term),
                )
            )
        if filters.event_type:
            conditions.append(AuditEvent.event_type == filters.event_type)
        if filters.outcome:
            conditions.append(AuditEvent.outcome == filters.outcome)
        if filters.actor_user_id:
            conditions.append(AuditEvent.actor_user_id == filters.actor_user_id)
        if filters.date_from:
            conditions.append(
                AuditEvent.occurred_at
                >= datetime.combine(filters.date_from, time.min, tzinfo=timezone.utc)
            )
        if filters.date_to:
            conditions.append(
                AuditEvent.occurred_at
                < datetime.combine(
                    filters.date_to + timedelta(days=1),
                    time.min,
                    tzinfo=timezone.utc,
                )
            )
        return conditions

    def list_events(self, filters: AuditFilters) -> AuditListResult:
        conditions = self._conditions(filters)
        joined = AuditEvent.__table__.outerjoin(
            User.__table__, User.user_id == AuditEvent.actor_user_id
        )
        total_count = int(
            self.db.scalar(
                select(func.count(AuditEvent.event_id))
                .select_from(joined)
                .where(*conditions)
            )
            or 0
        )
        total_pages = max(1, ceil(total_count / filters.page_size))
        page = min(max(1, filters.page), total_pages)
        rows = self.db.execute(
            select(AuditEvent, User.display_name, User.email)
            .select_from(joined)
            .where(*conditions)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.event_id.desc())
            .offset((page - 1) * filters.page_size)
            .limit(filters.page_size)
        ).all()

        event_types = tuple(
            self.db.scalars(
                select(AuditEvent.event_type)
                .where(AuditEvent.organization_id == self.organization_id)
                .distinct()
                .order_by(AuditEvent.event_type)
            ).all()
        )
        outcomes = tuple(
            self.db.scalars(
                select(AuditEvent.outcome)
                .where(AuditEvent.organization_id == self.organization_id)
                .distinct()
                .order_by(AuditEvent.outcome)
            ).all()
        )
        actor_rows = self.db.execute(
            select(User.user_id, User.display_name, User.email)
            .join(AuditEvent, AuditEvent.actor_user_id == User.user_id)
            .where(AuditEvent.organization_id == self.organization_id)
            .distinct()
            .order_by(User.display_name, User.email)
        ).all()
        actors = tuple(
            (user_id, f"{display_name} · {email}")
            for user_id, display_name, email in actor_rows
        )
        return AuditListResult(
            items=tuple(
                AuditRow(event, actor_name, actor_email)
                for event, actor_name, actor_email in rows
            ),
            page=page,
            page_size=filters.page_size,
            total_count=total_count,
            total_pages=total_pages,
            event_types=event_types,
            outcomes=outcomes,
            actors=actors,
        )

    def get_event(self, event_id: str) -> AuditRow | None:
        row = self.db.execute(
            select(AuditEvent, User.display_name, User.email)
            .outerjoin(User, User.user_id == AuditEvent.actor_user_id)
            .where(
                AuditEvent.event_id == event_id,
                AuditEvent.organization_id == self.organization_id,
            )
        ).one_or_none()
        if row is None:
            return None
        event, actor_name, actor_email = row
        return AuditRow(event, actor_name, actor_email)
