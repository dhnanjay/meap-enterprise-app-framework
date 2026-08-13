"""Notebook Phase 1 contract and security tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select

from app.platform.audit.models import AuditEvent
from app.platform.errors.taxonomy import ValidationError
from app.platform.notebooks.events import ALL_EVENTS, NOTEBOOK_REGISTERED
from app.platform.notebooks.models import NotebookEngine, NotebookMode
from app.platform.notebooks.permissions import (
    ALL_PERMISSIONS,
    NOTEBOOK_EDIT,
    PLATFORM_ADMIN_ONLY,
)
from app.platform.notebooks.registry import NotebookRegistration, NotebookRegistry
from app.settings import Settings


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PACKAGE = ROOT / "app" / "platform" / "notebooks"


def test_notebook_capability_is_disabled_by_default():
    assert Settings(_env_file=None).notebooks_enabled is False


def test_notebook_permission_vocabulary_is_complete_and_unique():
    assert len(ALL_PERMISSIONS) == 8
    assert len(set(ALL_PERMISSIONS)) == 8
    assert all(permission.count(".") == 2 for permission in ALL_PERMISSIONS)
    assert all(permission.startswith("platform.notebook.") for permission in ALL_PERMISSIONS)
    assert PLATFORM_ADMIN_ONLY == {NOTEBOOK_EDIT}


def test_notebook_audit_event_vocabulary_is_stable():
    assert NOTEBOOK_REGISTERED in ALL_EVENTS
    assert "notebook.runtime_started" in ALL_EVENTS
    assert "notebook.artifact_published" in ALL_EVENTS
    assert len(ALL_EVENTS) == len(set(ALL_EVENTS))


def test_register_external_notebook_creates_draft_and_audit(db_session):
    notebook = NotebookRegistry(db_session).register(
        NotebookRegistration(
            name="Variance analysis",
            engine=NotebookEngine.MARIMO,
            mode=NotebookMode.EXTERNAL,
            organization_id="org-1",
            external_url="https://notebooks.example.com/variance",
            created_by_user_id="user-1",
        ),
        correlation_id="corr-1",
    )

    assert notebook.name == "Variance analysis"
    assert notebook.status.value == "DRAFT"
    event = db_session.execute(
        select(AuditEvent).where(AuditEvent.entity_id == notebook.notebook_id)
    ).scalar_one()
    assert event.event_type == NOTEBOOK_REGISTERED
    assert event.organization_id == "org-1"
    assert event.actor_user_id == "user-1"
    assert event.correlation_id == "corr-1"


@pytest.mark.parametrize(
    "url",
    (
        "http://notebooks.example.com/unsafe",
        "javascript:alert(1)",
        "//notebooks.example.com/missing-scheme",
        "",
    ),
)
def test_external_notebooks_require_absolute_https(url, db_session):
    with pytest.raises(ValidationError) as exc:
        NotebookRegistry(db_session).register(
            NotebookRegistration(
                name="Unsafe",
                engine=NotebookEngine.MARIMO,
                mode=NotebookMode.EXTERNAL,
                external_url=url,
            )
        )
    assert exc.value.reason_code == "NOTEBOOK_EXTERNAL_URL_INVALID"


@pytest.mark.parametrize("path", ("../app/settings.py", "/etc/passwd", ""))
def test_local_notebook_source_cannot_escape_workspace(path, db_session):
    with pytest.raises(ValidationError) as exc:
        NotebookRegistry(db_session).register(
            NotebookRegistration(
                name="Unsafe",
                engine=NotebookEngine.MARIMO,
                mode=NotebookMode.APPLICATION,
                source_path=path,
                source_checksum="sha256:source",
                runtime_profile="marimo-pinned",
                environment_lock_hash="sha256:lock",
            )
        )
    assert exc.value.reason_code == "NOTEBOOK_SOURCE_PATH_INVALID"


def test_executable_registration_requires_reproducibility(db_session):
    with pytest.raises(ValidationError) as exc:
        NotebookRegistry(db_session).register(
            NotebookRegistration(
                name="Unpinned",
                engine=NotebookEngine.MARIMO,
                mode=NotebookMode.APPLICATION,
                source_path="variance.py",
            )
        )
    assert exc.value.reason_code == "NOTEBOOK_REPRODUCIBILITY_REQUIRED"


def test_editable_notebook_requires_platform_admin_permission(db_session):
    with pytest.raises(ValidationError) as exc:
        NotebookRegistry(db_session).register(
            NotebookRegistration(
                name="Shell-equivalent editor",
                engine=NotebookEngine.JUPYTER,
                mode=NotebookMode.EDITABLE,
                source_path="analysis.ipynb",
                source_checksum="sha256:source",
                runtime_profile="jupyter-pinned",
                environment_lock_hash="sha256:lock",
            )
        )
    assert exc.value.reason_code == "NOTEBOOK_EDIT_PERMISSION_REQUIRED"


def test_reproducible_notebook_definition_is_recorded(db_session):
    notebook = NotebookRegistry(db_session).register(
        NotebookRegistration(
            name="Pinned variance app",
            engine=NotebookEngine.MARIMO,
            mode=NotebookMode.APPLICATION,
            source_path="variance.py",
            source_checksum="sha256:source",
            runtime_profile="marimo-0.14-python-3.13",
            environment_lock_hash="sha256:lock",
        )
    )
    assert notebook.has_reproducible_runtime


def test_phase_one_has_no_execution_or_proxy_infrastructure():
    forbidden_import_roots = {
        "subprocess",
        "multiprocessing",
        "asyncio.subprocess",
        "websockets",
        "docker",
    }
    failures: list[str] = []
    for path in NOTEBOOK_PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in forbidden_import_roots
                ):
                    failures.append(f"{path.name}: {module}")
    assert not failures, "Phase 1 imported execution infrastructure: " + ", ".join(failures)


def test_phase_one_exposes_no_notebook_routes(client):
    paths = {
        path
        for route in client.app.routes
        if (path := getattr(route, "path", None)) is not None
    }
    assert not any(path.startswith("/notebooks") for path in paths)
