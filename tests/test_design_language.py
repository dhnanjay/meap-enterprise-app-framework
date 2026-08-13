"""Mechanical fitness checks for the normative MEAP design language."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_TEMPLATES = ROOT / "app" / "modules"
CSS = ROOT / "app" / "platform" / "static" / "css" / "meap.css"


def _module_templates() -> list[Path]:
    return sorted(MODULE_TEMPLATES.glob("*/templates/**/*.html"))


def test_module_templates_have_no_visual_literals():
    """Module templates receive design tokens through classes, not literals."""
    forbidden = re.compile(r"#[0-9a-fA-F]{3,8}|\b\d+(?:\.\d+)?(?:px|rem)\b")
    failures = []
    for template in _module_templates():
        if match := forbidden.search(template.read_text()):
            failures.append(f"{template.relative_to(ROOT)}: {match.group(0)}")
    assert not failures, "Visual literals found:\n" + "\n".join(failures)


def test_module_templates_use_normative_status_names():
    legacy = ("meap-badge--error", "meap-badge--info", "meap-btn--success")
    failures = []
    for template in _module_templates():
        text = template.read_text()
        for class_name in legacy:
            if class_name in text:
                failures.append(f"{template.relative_to(ROOT)}: {class_name}")
    assert not failures, "Legacy status classes found:\n" + "\n".join(failures)


def test_page_archetypes_are_declared():
    expected = {
        "app/modules/bank_reconciliation/templates/list.html": "meap-list-report",
        "app/modules/bank_reconciliation/templates/detail.html": "meap-object-page",
        "app/modules/bank_reconciliation/templates/exceptions.html": "meap-list-report",
        "app/modules/journal_entry_review/templates/list.html": "meap-list-report",
        "app/modules/journal_entry_review/templates/detail.html": "meap-object-page",
        "app/modules/journal_entry_review/templates/entries.html": "meap-list-report",
    }
    for relative, archetype in expected.items():
        assert archetype in (ROOT / relative).read_text(), relative


def test_object_pages_use_facts_not_kpi_cards():
    for relative in (
        "app/modules/bank_reconciliation/templates/detail.html",
        "app/modules/journal_entry_review/templates/detail.html",
    ):
        text = (ROOT / relative).read_text()
        assert "meap-facts" in text
        assert "meap-stat-card" not in text


def test_quiet_enterprise_tokens_and_print_contract_exist():
    css = CSS.read_text()
    required = (
        "--meap-attention-fg",
        "--meap-critical-fg",
        "--meap-row-height: 36px",
        '[data-density="comfortable"]',
        "font-variant-numeric: tabular-nums",
        "@media print",
    )
    for token in required:
        assert token in css


def test_collapsed_rail_keeps_main_out_of_the_zero_width_track():
    """The main region has explicit grid placement in every rail state."""
    css = CSS.read_text()
    assert ".meap-main-content { grid-column: 2;" in css
    assert ".meap-rail-collapsed .meap-main-content { grid-column: 1;" in css
    assert ".meap-rail-collapsed .meap-shell-body { grid-template-columns: minmax(0, 1fr);" in css


def test_design_language_artifacts_exist():
    spec = ROOT / "docs" / "MEAP-DESIGN-LANGUAGE.md"
    guide = ROOT / "docs" / "meap-styleguide.html"
    developer_guide = ROOT / "docs" / "DEVELOPER-CUSTOMIZATION-GUIDE.md"
    assert spec.is_file()
    assert guide.is_file()
    assert developer_guide.is_file()
    assert "../app/platform/static/css/meap.css" in guide.read_text()
    assert "docs/DEVELOPER-CUSTOMIZATION-GUIDE.md" in (ROOT / "README.md").read_text()
