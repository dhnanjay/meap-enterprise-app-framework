"""Access-control and workspace-isolation contract tests."""

from __future__ import annotations

import pytest

from app.modules.bank_reconciliation.schemas import ReconciliationQuery
from app.modules.bank_reconciliation.service import BankReconciliationService
from app.modules.journal_entry_review.schemas import JEReviewQuery
from app.modules.journal_entry_review.service import JournalEntryReviewService
from app.platform.auth.models import Membership, Organization, User
from app.platform.auth.service import AuthService
from app.platform.errors.taxonomy import NotFoundError
from app.platform.permissions.roles import expand_permission_patterns
from app.platform.registry.registry import build_registry
from app.settings import get_settings


REGISTERED_PERMISSIONS = frozenset(
    {
        "bank_reconciliation.reconciliation.view",
        "bank_reconciliation.reconciliation.create",
        "bank_reconciliation.reconciliation.execute",
        "bank_reconciliation.exception.resolve",
        "journal_entry_review.review.view",
        "journal_entry_review.entry.approve",
    }
)


def test_permission_patterns_expand_only_registered_permissions():
    assert expand_permission_patterns(
        frozenset({"*.view", "bank_reconciliation.*.execute"}),
        REGISTERED_PERMISSIONS,
    ) == frozenset(
        {
            "bank_reconciliation.reconciliation.view",
            "bank_reconciliation.reconciliation.execute",
            "journal_entry_review.review.view",
        }
    )


def test_registry_hides_navigation_without_its_required_permission():
    from app.modules.bank_reconciliation.module import MODULE as bank_module
    from app.modules.journal_entry_review.module import MODULE as journal_module

    registry = build_registry([bank_module, journal_module])
    navigation = registry.get_navigation(
        frozenset({"bank_reconciliation.reconciliation.view"})
    )
    visible_labels = {
        item["label"] for group in navigation for item in group["items"]
    }

    assert visible_labels == {"Bank Reconciliation"}


def test_membership_override_can_deny_role_permission(db_session):
    organization = Organization(name="Example Workspace", slug="example-workspace")
    user = User(
        email="operator@example.com",
        normalized_email="operator@example.com",
        display_name="Operator",
    )
    db_session.add_all([organization, user])
    db_session.flush()
    membership = Membership(
        organization_id=organization.organization_id,
        user_id=user.user_id,
        role="operator",
        status="active",
    )
    db_session.add(membership)
    db_session.flush()

    service = AuthService(db_session, get_settings())
    service.assign_role(membership, "operator", assigned_by_user_id=None)
    db_session.commit()

    permissions, roles = service.permissions_for_membership(
        membership.membership_id, REGISTERED_PERMISSIONS
    )
    assert "operator" in roles
    assert "bank_reconciliation.reconciliation.view" in permissions

    service.set_membership_permission(
        membership=membership,
        permission="bank_reconciliation.reconciliation.view",
        enabled=False,
        actor_user_id=user.user_id,
        registered_permissions=REGISTERED_PERMISSIONS,
    )
    permissions, _ = service.permissions_for_membership(
        membership.membership_id, REGISTERED_PERMISSIONS
    )
    assert "bank_reconciliation.reconciliation.view" not in permissions


def test_bank_reconciliation_records_are_workspace_scoped(db_session):
    workspace_a = BankReconciliationService(db_session, "workspace-a")
    workspace_b = BankReconciliationService(db_session, "workspace-b")

    record = workspace_a.create_reconciliation(
        reference="REC-001", account_name="Operating Cash", period="2026-08"
    )
    workspace_b.create_reconciliation(
        reference="REC-001", account_name="Other Cash", period="2026-08"
    )

    assert workspace_a.list_reconciliations(ReconciliationQuery()).total_count == 1
    assert workspace_b.list_reconciliations(ReconciliationQuery()).total_count == 1
    with pytest.raises(NotFoundError):
        workspace_b.get_detail(record.reconciliation_id)


def test_journal_review_records_are_workspace_scoped(db_session):
    workspace_a = JournalEntryReviewService(db_session, "workspace-a")
    workspace_b = JournalEntryReviewService(db_session, "workspace-b")

    record = workspace_a.create_review("Quarter close", "2026-Q3")

    assert workspace_a.list_reviews(JEReviewQuery()).total_count == 1
    assert workspace_b.list_reviews(JEReviewQuery()).total_count == 0
    with pytest.raises(NotFoundError):
        workspace_b.get_detail(record.review_id)
