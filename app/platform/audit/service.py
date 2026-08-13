"""Append-only audit writer.

This service intentionally exposes no update or delete operation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform.audit.models import AuditEvent


class AuditService:
    """Create durable audit records without exposing mutation APIs."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        *,
        event_type: str,
        outcome: str = "SUCCEEDED",
        organization_id: str | None = None,
        actor_user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        runtime_profile: str | None = None,
        notebook_version: str | None = None,
        environment_lock_hash: str | None = None,
        data_snapshot_id: str | None = None,
        input_artifact_ids: list[str] | None = None,
        output_artifact_ids: list[str] | None = None,
        event_data: dict | None = None,
        commit: bool = True,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            outcome=outcome,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            runtime_profile=runtime_profile,
            notebook_version=notebook_version,
            environment_lock_hash=environment_lock_hash,
            data_snapshot_id=data_snapshot_id,
            input_artifact_ids=input_artifact_ids,
            output_artifact_ids=output_artifact_ids,
            event_data=event_data,
        )
        self._db.add(event)
        if commit:
            self._db.commit()
            self._db.refresh(event)
        else:
            self._db.flush()
        return event
