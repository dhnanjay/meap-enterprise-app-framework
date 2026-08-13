"""Validated persistence boundary for notebook definitions.

No execution behavior belongs in this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform.audit.service import AuditService
from app.platform.errors.taxonomy import ValidationError
from app.platform.notebooks.events import NOTEBOOK_REGISTERED
from app.platform.notebooks.models import (
    NotebookDefinition,
    NotebookEngine,
    NotebookMode,
    NotebookStatus,
)
from app.platform.notebooks.permissions import NOTEBOOK_EDIT, NOTEBOOK_VIEW


@dataclass(frozen=True)
class NotebookRegistration:
    name: str
    engine: NotebookEngine
    mode: NotebookMode
    organization_id: str | None = None
    description: str = ""
    external_url: str | None = None
    source_path: str | None = None
    source_checksum: str | None = None
    runtime_profile: str | None = None
    environment_lock_hash: str | None = None
    required_permission: str = NOTEBOOK_VIEW
    created_by_user_id: str | None = None


class NotebookRegistry:
    """Register and query typed notebook definitions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def register(
        self,
        registration: NotebookRegistration,
        *,
        correlation_id: str | None = None,
    ) -> NotebookDefinition:
        self._validate(registration)
        notebook = NotebookDefinition(
            organization_id=registration.organization_id,
            name=registration.name.strip(),
            description=registration.description,
            engine=registration.engine,
            mode=registration.mode,
            status=NotebookStatus.DRAFT,
            external_url=registration.external_url,
            source_path=registration.source_path,
            source_checksum=registration.source_checksum,
            runtime_profile=registration.runtime_profile,
            environment_lock_hash=registration.environment_lock_hash,
            required_permission=registration.required_permission,
            created_by_user_id=registration.created_by_user_id,
            updated_by_user_id=registration.created_by_user_id,
        )
        self._db.add(notebook)
        self._db.flush()
        AuditService(self._db).record(
            event_type=NOTEBOOK_REGISTERED,
            organization_id=registration.organization_id,
            actor_user_id=registration.created_by_user_id,
            entity_type="notebook",
            entity_id=notebook.notebook_id,
            correlation_id=correlation_id,
            notebook_version=registration.source_checksum,
            runtime_profile=registration.runtime_profile,
            environment_lock_hash=registration.environment_lock_hash,
            event_data={
                "engine": registration.engine.value,
                "mode": registration.mode.value,
            },
            commit=False,
        )
        self._db.commit()
        self._db.refresh(notebook)
        return notebook

    def get(self, notebook_id: str) -> NotebookDefinition | None:
        return self._db.get(NotebookDefinition, notebook_id)

    def list_for_organization(
        self, organization_id: str | None
    ) -> list[NotebookDefinition]:
        stmt = (
            select(NotebookDefinition)
            .where(NotebookDefinition.organization_id == organization_id)
            .order_by(NotebookDefinition.name.asc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def _validate(self, registration: NotebookRegistration) -> None:
        if not registration.name.strip():
            self._invalid("NOTEBOOK_NAME_REQUIRED", "Notebook name is required.")

        if registration.mode == NotebookMode.EXTERNAL:
            parsed = urlparse(registration.external_url or "")
            if parsed.scheme != "https" or not parsed.hostname:
                self._invalid(
                    "NOTEBOOK_EXTERNAL_URL_INVALID",
                    "External notebook URLs must use HTTPS and include a hostname.",
                )
            if registration.source_path is not None:
                self._invalid(
                    "NOTEBOOK_EXTERNAL_SOURCE_CONFLICT",
                    "External notebook definitions cannot include a local source path.",
                )
            return

        if registration.external_url is not None:
            self._invalid(
                "NOTEBOOK_LOCAL_URL_CONFLICT",
                "Local notebook definitions cannot include an external URL.",
            )

        source = PurePosixPath(registration.source_path or "")
        if (
            not registration.source_path
            or source.is_absolute()
            or ".." in source.parts
        ):
            self._invalid(
                "NOTEBOOK_SOURCE_PATH_INVALID",
                "Notebook source must be a relative path inside the configured workspace.",
            )

        expected_suffix = ".py" if registration.engine == NotebookEngine.MARIMO else ".ipynb"
        if source.suffix.lower() != expected_suffix:
            self._invalid(
                "NOTEBOOK_SOURCE_TYPE_INVALID",
                f"{registration.engine.value.title()} notebooks must use {expected_suffix} files.",
            )

        if not (
            registration.source_checksum
            and registration.runtime_profile
            and registration.environment_lock_hash
        ):
            self._invalid(
                "NOTEBOOK_REPRODUCIBILITY_REQUIRED",
                "Executable notebook definitions require source, runtime, and lockfile hashes.",
            )

        if (
            registration.mode == NotebookMode.EDITABLE
            and registration.required_permission != NOTEBOOK_EDIT
        ):
            self._invalid(
                "NOTEBOOK_EDIT_PERMISSION_REQUIRED",
                "Editable notebooks require the platform-admin-only notebook edit permission.",
            )

    @staticmethod
    def _invalid(reason_code: str, safe_message: str) -> None:
        raise ValidationError(
            module="platform",
            operation="register_notebook",
            reason_code=reason_code,
            safe_message=safe_message,
        )
