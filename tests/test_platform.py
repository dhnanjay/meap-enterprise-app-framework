"""Platform tests: registry, query_state, error taxonomy (Section 59)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter

from app.platform.errors.taxonomy import (
    ErrorCategory,
    MeapError,
    NotFoundError,
    ValidationError,
)
from app.platform.registry.definitions import (
    DuplicateModuleError,
    ModuleContractError,
    ModuleDefinition,
    NavigationDefinition,
)
from app.platform.registry.registry import ModuleRegistry, build_registry
from app.platform.templates.query_state import (
    PageQuery,
    SortDirection,
    SortMapper,
    query_url,
)


# ── Registry Tests (Sections 8, 9, 10) ────────────────────────────────────────


def _make_definition(
    id: str = "test_module",
    name: str = "Test Module",
    prefix: str = "/test",
    permissions: tuple = (),
    nav: bool | NavigationDefinition = True,
    enabled: bool = True,
) -> ModuleDefinition:
    if not permissions:
        permissions = (f"{id}.view",)
    if isinstance(nav, NavigationDefinition):
        nav_def = nav
    elif nav:
        nav_def = NavigationDefinition(label=name, group="Test")
    else:
        nav_def = None

    return ModuleDefinition(
        id=id,
        name=name,
        route_prefix=prefix,
        router=APIRouter(),
        permissions=permissions,
        navigation=nav_def,
        enabled=enabled,
    )


class TestModuleRegistry:
    """Registry contract tests (Section 8, 9, 10, 60)."""

    def test_register_single_module(self):
        """A module registers and is queryable."""
        reg = ModuleRegistry()
        reg.register(_make_definition())
        assert "test_module" in reg.modules
        assert reg.get("test_module") is not None

    def test_register_disabled_module(self):
        """A disabled module does not appear (Section 10)."""
        reg = ModuleRegistry()
        reg.register(_make_definition(enabled=False))
        assert "test_module" not in reg.modules
        assert len(reg.all_permissions) == 0

    def test_duplicate_id_rejected(self):
        """Two modules with same id raises DuplicateModuleError."""
        reg = ModuleRegistry()
        reg.register(_make_definition())
        with pytest.raises(DuplicateModuleError):
            reg.register(_make_definition())

    def test_duplicate_route_prefix_rejected(self):
        """Two modules with same route_prefix raises DuplicateModuleError."""
        reg = ModuleRegistry()
        reg.register(_make_definition(id="a", prefix="/x"))
        with pytest.raises(DuplicateModuleError):
            reg.register(_make_definition(id="b", prefix="/x"))

    def test_duplicate_permission_rejected(self):
        """Same permission in two modules raises DuplicateModuleError (Section 61)."""
        reg = ModuleRegistry()
        reg.register(_make_definition(id="a", permissions=("shared.perm",)))
        with pytest.raises(DuplicateModuleError):
            reg.register(_make_definition(
                id="b", prefix="/y", permissions=("shared.perm",)
            ))

    def test_invalid_id_rejected(self):
        """Non-snake_case id raises ModuleContractError."""
        reg = ModuleRegistry()
        with pytest.raises(ModuleContractError):
            reg.register(_make_definition(id="Bad-ID!"))

    def test_empty_name_rejected(self):
        """Empty name raises ModuleContractError."""
        reg = ModuleRegistry()
        with pytest.raises(ModuleContractError):
            reg.register(_make_definition(name="   "))

    def test_prefix_must_start_with_slash(self):
        """Route prefix without leading slash raises ModuleContractError."""
        reg = ModuleRegistry()
        with pytest.raises(ModuleContractError):
            reg.register(_make_definition(prefix="no-slash"))

    def test_permissions_registered(self):
        """Permissions are exposed after registration (Section 41)."""
        reg = ModuleRegistry()
        reg.register(_make_definition(permissions=("mod.read", "mod.write")))
        assert reg.has_permission("mod.read")
        assert reg.has_permission("mod.write")
        assert not reg.has_permission("mod.delete")

    def test_navigation_grouped(self):
        """Navigation is grouped and ordered (Section 12)."""
        reg = ModuleRegistry()
        reg.register(_make_definition(
            id="mod_a",
            prefix="/a",
            nav=NavigationDefinition(label="A", group="Group1", order=20),
        ))
        reg.register(_make_definition(
            id="mod_b",
            prefix="/b",
            nav=NavigationDefinition(label="B", group="Group1", order=10),
        ))
        reg.register(_make_definition(
            id="mod_c",
            prefix="/c",
            nav=NavigationDefinition(label="C", group="Group2", order=5),
        ))
        nav = reg.get_navigation()
        assert len(nav) == 2
        assert nav[0]["group"] == "Group1"
        assert nav[0]["items"][0]["label"] == "B"  # order=10 first
        assert nav[0]["items"][1]["label"] == "A"  # order=20 second

    def test_build_registry(self):
        """build_registry from list works (Section 9)."""
        defs = [
            _make_definition(id=f"mod_{i}", prefix=f"/m{i}", permissions=(f"mod_{i}.view",))
            for i in range(3)
        ]
        reg = build_registry(defs)
        assert len(reg.modules) == 3

    def test_independence_disable(self):
        """Independence Test (Section 60): disabling one module doesn't affect others."""
        reg = ModuleRegistry()
        reg.register(_make_definition(id="mod_a", prefix="/a"))
        # If we had mod_b disabled, mod_a should still work
        reg.register(_make_definition(id="mod_c", prefix="/c", enabled=False))
        assert "mod_a" in reg.modules
        assert "mod_c" not in reg.modules


# ── Query State Tests (URL-State Architecture) ─────────────────────────────────


class TestQueryState:
    """URL-as-state tests (Section: URL and Query-State Architecture)."""

    def test_page_query_defaults(self):
        q = PageQuery()
        assert q.page == 1
        assert q.page_size == 25
        assert q.offset == 0
        assert not q.is_desc

    def test_page_query_offset(self):
        q = PageQuery(page=3, page_size=50)
        assert q.offset == 100

    def test_page_query_desc(self):
        q = PageQuery(direction=SortDirection.DESC)
        assert q.is_desc

    def test_query_url_set(self):
        """query_url with set_ overrides params."""
        from starlette.datastructures import QueryParams
        params = QueryParams("status=OPEN&page=2")
        result = query_url(params, set_={"status": "CLOSED"})
        assert "status=CLOSED" in result
        assert "page=2" in result

    def test_query_url_reset(self):
        """query_url with reset overrides params."""
        from starlette.datastructures import QueryParams
        params = QueryParams("status=OPEN&page=5")
        result = query_url(params, set_={"status": "CLOSED"}, reset={"page": 1})
        assert "page=1" in result

    def test_query_url_empty_returns_empty(self):
        """No params → empty string."""
        from starlette.datastructures import QueryParams
        result = query_url(QueryParams(""))
        assert result == ""

    def test_query_url_remove(self):
        """Applied-filter pills can remove one URL-state key."""
        from starlette.datastructures import QueryParams
        result = query_url(
            QueryParams("status=OPEN&q=bank&page=3"),
            remove={"status"},
            reset={"page": 1},
        )
        assert "status=" not in result
        assert "q=bank" in result
        assert "page=1" in result

    def test_sort_mapper_valid(self):
        """SortMapper resolves valid column names."""
        mapper = SortMapper({"amount": "amount_col", "date": "date_col"})
        assert mapper.resolve("amount") == "amount_col"
        assert mapper.resolve("date") == "date_col"

    def test_sort_mapper_invalid(self):
        """SortMapper returns None for unknown columns (security)."""
        mapper = SortMapper({"amount": "amount_col"})
        assert mapper.resolve("malicious_drop_table") is None
        assert mapper.resolve(None) is None

    def test_sort_mapper_allowed(self):
        mapper = SortMapper({"a": "col_a", "b": "col_b"})
        assert set(mapper.allowed) == {"a", "b"}


# ── Error Taxonomy Tests (Sections 44, 45) ─────────────────────────────────────


class TestErrorTaxonomy:
    """Error envelope and taxonomy tests."""

    def test_error_has_id_and_correlation(self):
        err = NotFoundError(
            module="test",
            operation="get",
            reason_code="NOT_FOUND",
            safe_message="Not found",
            correlation_id="CORR-123",
        )
        assert err.error_id.startswith("ERR-")
        assert err.correlation_id == "CORR-123"
        assert err.category == ErrorCategory.NOT_FOUND
        assert err.http_status == 404

    def test_error_envelope(self):
        err = ValidationError(
            module="br",
            operation="create",
            reason_code="BAD_INPUT",
            safe_message="Invalid input",
        )
        env = err.to_envelope()
        assert env["module"] == "br"
        assert env["operation"] == "create"
        assert env["category"] == "VALIDATION"
        assert env["reason_code"] == "BAD_INPUT"
        assert "error_id" in env
        assert "timestamp" in env

    def test_validation_error_status(self):
        err = ValidationError(
            module="x", operation="y", reason_code="Z", safe_message="msg"
        )
        assert err.http_status == 422

    def test_all_categories_exist(self):
        """All 11 canonical categories exist (Section 44)."""
        expected = {
            "VALIDATION", "AUTHENTICATION", "AUTHORIZATION", "NOT_FOUND",
            "CONFLICT", "DOMAIN", "DATA", "INTEGRATION", "JOB", "ARTIFACT", "SYSTEM",
        }
        actual = {c.value for c in ErrorCategory}
        assert actual == expected
