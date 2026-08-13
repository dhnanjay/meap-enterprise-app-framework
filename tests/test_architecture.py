"""Architecture Fitness Tests (Section 61).

Enforces structural rules automatically:
- Platform cannot import modules
- Module A cannot import module B internals
- Routes cannot import repositories directly (should go through service)
- Permissions are registered uniquely
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM_DIR = _PROJECT_ROOT / "app" / "platform"
_MODULES_DIR = _PROJECT_ROOT / "app" / "modules"


def _collect_python_files(base: Path) -> list[Path]:
    """Collect all .py files under a directory."""
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    """Extract all import module paths from a Python file using AST."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


# ── Platform Isolation Tests (Section 42, 61) ──────────────────────────────────


class TestPlatformIsolation:
    """The Platform must never import from business modules (Section 6, 42)."""

    @pytest.mark.parametrize("py_file", _collect_python_files(_PLATFORM_DIR))
    def test_platform_does_not_import_modules(self, py_file: Path):
        """No platform file imports from app.modules.*"""
        imports = _get_imports(py_file)
        for imp in imports:
            assert not imp.startswith("app.modules."), (
                f"Platform file {py_file.relative_to(_PROJECT_ROOT)} "
                f"imports from business module: {imp}"
            )


# ── Module Isolation Tests (Section 42, 61) ────────────────────────────────────


class TestModuleIsolation:
    """A business module may not import implementation internals from another (Section 42)."""

    MODULE_NAMES = ["bank_reconciliation", "journal_entry_review"]

    def test_no_cross_module_imports(self):
        """Module A does not import from Module B's internals."""
        for mod_name in self.MODULE_NAMES:
            mod_dir = _MODULES_DIR / mod_name
            if not mod_dir.exists():
                continue
            for py_file in _collect_python_files(mod_dir):
                rel = py_file.relative_to(_PROJECT_ROOT)
                imports = _get_imports(py_file)
                for imp in imports:
                    for other_mod in self.MODULE_NAMES:
                        if other_mod == mod_name:
                            continue
                        forbidden = f"app.modules.{other_mod}"
                        assert not imp.startswith(forbidden), (
                            f"Module {mod_name} file {rel} "
                            f"imports from another module: {imp}"
                        )


# ── Registry Uniqueness Tests (Section 61) ─────────────────────────────────────


class TestRegistryUniqueness:
    """Permissions are registered uniquely (Section 61)."""

    def test_no_duplicate_permissions(self):
        from app.modules.bank_reconciliation.module import MODULE as BRModule
        from app.modules.journal_entry_review.module import MODULE as JEModule

        all_perms = list(BRModule.permissions) + list(JEModule.permissions)
        assert len(all_perms) == len(set(all_perms)), "Duplicate permissions detected"

    def test_no_duplicate_route_prefixes(self):
        from app.modules.bank_reconciliation.module import MODULE as BRModule
        from app.modules.journal_entry_review.module import MODULE as JEModule

        prefixes = [BRModule.route_prefix, JEModule.route_prefix]
        assert len(prefixes) == len(set(prefixes))

    def test_no_duplicate_ids(self):
        from app.modules.bank_reconciliation.module import MODULE as BRModule
        from app.modules.journal_entry_review.module import MODULE as JEModule

        ids = [BRModule.id, JEModule.id]
        assert len(ids) == len(set(ids))


# ── Layer Discipline Tests (Section 61) ────────────────────────────────────────


class TestLayerDiscipline:
    """Routes cannot import repositories directly (should go through service)."""

    MODULE_NAMES = ["bank_reconciliation", "journal_entry_review"]

    @pytest.mark.parametrize("mod_name", MODULE_NAMES)
    def test_routes_no_direct_repository_import(self, mod_name: str):
        """routes.py should not import from repository.py directly (Section 26)."""
        routes_file = _MODULES_DIR / mod_name / "routes.py"
        if not routes_file.exists():
            pytest.skip(f"No routes.py for {mod_name}")

        imports = _get_imports(routes_file)
        for imp in imports:
            assert "repository" not in imp, (
                f"{mod_name}/routes.py imports repository directly: {imp}. "
                f"Routes should go through service layer."
            )