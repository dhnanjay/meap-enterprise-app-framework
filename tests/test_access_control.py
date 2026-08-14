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


def test_access_panel_links_come_only_from_live_module_registry():
    from app.modules.bank_reconciliation.module import MODULE as bank_module
    from app.modules.journal_entry_review.module import MODULE as journal_module

    both = build_registry([bank_module, journal_module])
    assert [item["label"] for item in both.get_configurable_navigation()] == [
        "Bank Reconciliation",
        "JE Review",
    ]

    without_journal = build_registry([bank_module])
    assert [
        item["label"] for item in without_journal.get_configurable_navigation()
    ] == ["Bank Reconciliation"]


def test_new_registered_navigation_link_automatically_enters_access_panel():
    from fastapi import APIRouter

    from app.platform.registry.definitions import ModuleDefinition, NavigationDefinition

    permission = "data_operations.queue.view"
    module = ModuleDefinition(
        id="data_operations",
        name="Data Operations",
        route_prefix="/data-operations",
        router=APIRouter(),
        permissions=(permission,),
        navigation=NavigationDefinition(
            label="Data Operations",
            group="Operations",
            required_permission=permission,
        ),
    )

    registry = build_registry([module])
    assert registry.get_configurable_navigation() == [
        {
            "module_id": "data_operations",
            "label": "Data Operations",
            "group": "Operations",
            "order": 100,
            "icon": None,
            "href": "/data-operations",
            "required_permission": permission,
        }
    ]


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


def test_custom_role_uses_registered_exact_permissions_and_workspace_scope(
    db_session,
):
    organization = Organization(name="Primary Workspace", slug="primary-workspace")
    other = Organization(name="Other Workspace", slug="other-workspace")
    user = User(
        email="steward@example.com",
        normalized_email="steward@example.com",
        display_name="Data Steward",
    )
    db_session.add_all([organization, other, user])
    db_session.flush()
    membership = Membership(
        organization_id=organization.organization_id,
        user_id=user.user_id,
        role="viewer",
        status="active",
    )
    db_session.add(membership)
    db_session.flush()
    service = AuthService(db_session, get_settings())

    role = service.create_access_role(
        organization_id=organization.organization_id,
        display_name="Data Steward",
        description="Maintains operational data without execution rights.",
        actor_user_id=user.user_id,
    )
    service.update_access_role(
        role=role,
        organization_id=organization.organization_id,
        display_name=role.display_name,
        description=role.description,
        permissions=frozenset(
            {
                "bank_reconciliation.reconciliation.view",
                "journal_entry_review.review.view",
            }
        ),
        registered_permissions=REGISTERED_PERMISSIONS,
        actor_user_id=user.user_id,
    )
    service.assign_role(membership, role.role_key, assigned_by_user_id=user.user_id)
    db_session.commit()

    permissions, roles = service.permissions_for_membership(
        membership.membership_id, REGISTERED_PERMISSIONS
    )
    assert roles == (role.role_key,)
    assert permissions == frozenset(
        {
            "bank_reconciliation.reconciliation.view",
            "journal_entry_review.review.view",
        }
    )
    assert service.get_access_role(other.organization_id, role.role_id) is None
    with pytest.raises(ValueError, match="not found"):
        service.update_access_role(
            role=role,
            organization_id=other.organization_id,
            display_name=role.display_name,
            description=role.description,
            permissions=frozenset(),
            registered_permissions=REGISTERED_PERMISSIONS,
            actor_user_id=user.user_id,
        )


def test_workspace_administrator_role_cannot_be_reduced(db_session):
    organization = Organization(name="Protected Workspace", slug="protected-workspace")
    db_session.add(organization)
    db_session.flush()
    service = AuthService(db_session, get_settings())
    administrator_role = service.ensure_default_roles(organization.organization_id)[
        "workspace_admin"
    ]

    with pytest.raises(ValueError, match="fixed"):
        service.update_access_role(
            role=administrator_role,
            organization_id=organization.organization_id,
            display_name=administrator_role.display_name,
            description=administrator_role.description,
            permissions=frozenset(),
            registered_permissions=REGISTERED_PERMISSIONS,
            actor_user_id="administrator",
        )


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
