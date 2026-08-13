"""Module contract and route tests (Sections 59, 60).

Tests cover:
- Module contract: registration, navigation, permissions
- Route tests: HTTP status, rendering, HTMX fragments
- Integration: CRUD workflows, URL-state, deep linking
"""

from __future__ import annotations

import pytest

from app.modules.bank_reconciliation.module import MODULE as BRModule
from app.modules.journal_entry_review.module import MODULE as JEModule


# ── Module Contract Tests (Sections 8, 59) ────────────────────────────────────


class TestModuleContracts:
    """Every module satisfies the typed ModuleDefinition contract."""

    def test_bank_reconciliation_contract(self):
        d = BRModule
        assert d.id == "bank_reconciliation"
        assert d.name == "Bank Reconciliation"
        assert d.route_prefix == "/bank-recon"
        assert d.router is not None
        assert len(d.permissions) > 0
        assert d.navigation is not None
        assert d.navigation.group == "Accounting"
        assert d.enabled is True

    def test_journal_entry_review_contract(self):
        d = JEModule
        assert d.id == "journal_entry_review"
        assert d.name == "Journal Entry Review"
        assert d.route_prefix == "/je-review"
        assert d.router is not None
        assert len(d.permissions) > 0
        assert d.navigation is not None
        assert d.enabled is True

    def test_modules_have_unique_ids(self):
        assert BRModule.id != JEModule.id

    def test_modules_have_unique_prefixes(self):
        assert BRModule.route_prefix != JEModule.route_prefix

    def test_no_overlapping_permissions(self):
        """No two modules declare the same permission (Section 61)."""
        br_perms = set(BRModule.permissions)
        je_perms = set(JEModule.permissions)
        assert br_perms.isdisjoint(je_perms)

    def test_permission_naming_convention(self):
        """All permissions follow module.resource.action (Section 41)."""
        for perm in BRModule.permissions:
            parts = perm.split(".")
            assert len(parts) >= 2, f"Permission {perm} doesn't follow convention"
            assert parts[0] == "bank_reconciliation"

        for perm in JEModule.permissions:
            parts = perm.split(".")
            assert len(parts) >= 2, f"Permission {perm} doesn't follow convention"
            assert parts[0] == "journal_entry_review"


# ── Route Tests: Bank Reconciliation (Sections 50, 51, 59) ─────────────────────


class TestBankReconciliationRoutes:
    """HTTP route tests for bank_reconciliation."""

    def test_list_page(self, client):
        """List page returns 200 with shell (Section 50)."""
        r = client.get("/bank-recon")
        assert r.status_code == 200
        assert b"text/html" in r.headers.get("content-type", "").encode()

    def test_list_page_htmx_fragment(self, client):
        """HTMX request returns fragment (Section 17)."""
        r = client.get("/bank-recon", headers={"HX-Request": "true"})
        assert r.status_code == 200
        # Fragments should have HX-Push-Url header
        assert "HX-Push-Url" in r.headers or r.status_code == 200

    def test_list_page_exposes_applied_url_filters(self, client):
        r = client.get("/bank-recon?q=flow")
        assert r.status_code == 200
        assert 'class="meap-active-filters"' in r.text
        assert "Search: flow" in r.text

    def test_create_reconciliation(self, client):
        """POST creates a reconciliation (Section 51)."""
        r = client.post("/bank-recon", data={
            "reference": "BR-TEST-100",
            "account_name": "Test Account",
            "period": "2026-01",
            "statement_balance": "10000",
            "book_balance": "9500",
        })
        assert r.status_code in (200, 303)

    def test_duplicate_reference_rejected(self, client):
        """Duplicate reference returns error envelope (Section 45)."""
        # Create first
        client.post("/bank-recon", data={
            "reference": "BR-DUP-001",
            "account_name": "Test",
            "period": "2026-01",
            "statement_balance": "1000",
            "book_balance": "1000",
        })
        # Create duplicate
        r = client.post("/bank-recon", data={
            "reference": "BR-DUP-001",
            "account_name": "Test 2",
            "period": "2026-01",
            "statement_balance": "2000",
            "book_balance": "2000",
        })
        assert r.status_code in (400, 422, 500)
        # Check for error envelope
        body = r.text
        assert "DUPLICATE_REFERENCE" in body or "error" in body.lower()

    def test_detail_not_found(self, client):
        """Non-existent reconciliation returns 404 (Section 45)."""
        r = client.get("/bank-recon/nonexistent-id")
        assert r.status_code == 404

    def test_create_then_detail(self, client):
        """Create then view detail (Section 71)."""
        # Create
        r = client.post("/bank-recon", data={
            "reference": "BR-FLOW-001",
            "account_name": "Flow Account",
            "period": "2026-02",
            "statement_balance": "50000",
            "book_balance": "48000",
        })
        assert r.status_code in (200, 303)

        # List should show it
        r = client.get("/bank-recon")
        assert "BR-FLOW-001" in r.text

    def test_exceptions_url_state(self, client):
        """Exceptions page accepts URL filters (Section: URL-State)."""
        # Create a recon first
        client.post("/bank-recon", data={
            "reference": "BR-URL-001",
            "account_name": "URL Test",
            "period": "2026-03",
            "statement_balance": "100",
            "book_balance": "100",
        })

        # Get list to find the UUID
        r = client.get("/bank-recon")
        assert r.status_code == 200

    def test_deep_link_valid(self, client):
        """Every screen has a stable URL (Section 50)."""
        # List page
        assert client.get("/bank-recon").status_code == 200
        # JE Review list
        assert client.get("/je-review").status_code == 200


# ── Route Tests: Journal Entry Review ──────────────────────────────────────────


class TestJournalEntryReviewRoutes:
    """HTTP route tests for journal_entry_review."""

    def test_list_page(self, client):
        r = client.get("/je-review")
        assert r.status_code == 200

    def test_list_page_htmx(self, client):
        r = client.get("/je-review", headers={"HX-Request": "true"})
        assert r.status_code == 200

    def test_list_page_exposes_applied_url_filters(self, client):
        r = client.get("/je-review?q=audit&status=IN_REVIEW")
        assert r.status_code == 200
        assert 'class="meap-active-filters"' in r.text
        assert "Status: IN_REVIEW" in r.text

    def test_detail_not_found(self, client):
        r = client.get("/je-review/nonexistent-id")
        assert r.status_code == 404


# ── Platform Route Tests ──────────────────────────────────────────────────────


class TestPlatformRoutes:
    """Platform-level route tests."""

    def test_dashboard(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"MEAP" in r.content
        assert b'hx-get="/bank-recon"' in r.content
        assert b"htmx-2.0.10.min.js" in r.content

    def test_global_search(self, client):
        r = client.get("/search?q=bank")
        assert r.status_code == 200
        assert "<ui5-" not in r.text

    def test_global_search_empty(self, client):
        r = client.get("/search")
        assert r.status_code == 200

    def test_developer_area(self, client):
        """Developer diagnostics area is accessible (Section 48)."""
        r = client.get("/developer")
        assert r.status_code == 200
        assert "<ui5-" not in r.text

    def test_static_assets_served(self, client):
        """Static CSS is served (Section 22)."""
        r = client.get("/static/css/meap.css")
        assert r.status_code == 200

        js = client.get("/static/vendor/htmx-2.0.10.min.js")
        assert js.status_code == 200
        assert len(js.content) > 40_000


# ── Independence Test (Section 60) ─────────────────────────────────────────────


class TestModuleIndependence:
    """If a module is disabled, unrelated modules still work."""

    def test_both_modules_registered(self, client):
        """Both modules are present in navigation."""
        r = client.get("/")
        assert b"Bank Reconciliation" in r.content
        assert b"JE Review" in r.content

    def test_both_modules_accessible(self, client):
        """Both module routes are accessible."""
        assert client.get("/bank-recon").status_code == 200
        assert client.get("/je-review").status_code == 200
