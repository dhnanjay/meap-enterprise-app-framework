"""Rendering utilities — Jinja environment and render_page (Section 17).

Every routable page must support:
    - Direct URL access
    - Browser refresh
    - HTMX navigation
    - Back / Forward
    - Deep linking

render_page centralizes the full-page vs fragment decision.
Individual developers should not repeatedly implement HX-Request checks.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.platform.templates.query_state import query_url, query_url_path

# Template directories: platform shell + each module
_BASE_DIR = Path(__file__).resolve().parent  # app/platform/templates/
_PLATFORM_DIR = _BASE_DIR.parent  # app/platform/

# Shell templates are loaded directly (no prefix):
#   "dashboard.html", "shell_page.html", etc.
# Module templates use a PrefixLoader keyed by module id:
#   "bank_reconciliation/list.html" -> app/modules/bank_reconciliation/templates/list.html
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

_shell_dir = _PLATFORM_DIR / "shell" / "templates"
# Modules live at app/modules/, NOT app/platform/modules/
_modules_dir = _PLATFORM_DIR.parent / "modules"

_module_mapping: dict[str, FileSystemLoader] = {}
if _modules_dir.exists():
    for _module_dir in sorted(_modules_dir.iterdir()):
        _tpl = _module_dir / "templates"
        if _tpl.is_dir():
            _module_mapping[_module_dir.name] = FileSystemLoader(str(_tpl))

templates = Jinja2Templates(directory=str(_shell_dir))
templates.env.loader = ChoiceLoader(
    [
        FileSystemLoader(str(_shell_dir)),  # shell templates (no prefix)
        PrefixLoader(_module_mapping),  # module templates (prefix = module id)
    ]
)

# Register query_state helpers as Jinja globals
templates.env.globals["query_url"] = query_url
templates.env.globals["query_url_path"] = query_url_path


def is_htmx_request(request: Request) -> bool:
    """Check if this is an HTMX-initiated request."""
    return request.headers.get("HX-Request") == "true"


def is_history_restore(request: Request) -> bool:
    """Check if this is an HTMX history restoration request."""
    return request.headers.get("HX-History-Restore-Request") == "true"


def render_page(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    full_template: str | None = None,
    target: str = "main-content",
) -> HTMLResponse:
    """Render a page or fragment based on the request type (Section 17).

    For a normal HTTP request: renders the full document (shell + content).
    For an HTMX request: renders only the content fragment.

    Args:
        request: The FastAPI request.
        template_name: The fragment/content template path.
        context: Template context variables.
        full_template: Override the shell template (defaults to "shell_page.html").
        target: The DOM ID to swap content into for HTMX.
    """
    ctx = context or {}
    ctx.setdefault("request", request)

    # Inject common context
    registry = getattr(request.app.state, "registry", None)
    if registry is not None:
        ctx.setdefault("navigation", registry.get_navigation())
        ctx.setdefault("modules", registry.diagnostic_snapshot())
        ctx.setdefault("all_permissions", registry.all_permissions)
    ctx.setdefault(
        "correlation_id", getattr(request.state, "correlation_id", None)
    )
    ctx.setdefault("current_path", request.url.path)
    ctx.setdefault("current_query", request.query_params)
    settings = getattr(request.app.state, "settings", None)
    ctx.setdefault("settings", settings)
    ctx.setdefault("developer_area_enabled", settings.developer_area_enabled if settings else False)
    # Templates always render progressive-enhancement attributes. Native href,
    # action, and method remain authoritative when JavaScript is unavailable.
    # Request-type detection below still decides fragment vs full-page output.
    ctx.setdefault("request_is_htmx", is_htmx_request(request))
    ctx.setdefault("is_htmx", True)

    if is_htmx_request(request):
        # HTMX: return fragment only, add out-of-band swap for nav if needed
        response = templates.TemplateResponse(request, template_name, ctx)
        response.headers["HX-Push-Url"] = str(request.url)
        return response

    # Full page: wrap fragment in the shell
    shell = full_template or "shell_page.html"
    ctx["content_template"] = template_name
    ctx["content_target"] = target
    return templates.TemplateResponse(request, shell, ctx)


def render_fragment(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> HTMLResponse:
    """Always render a fragment, regardless of HX-Request (for partial swaps)."""
    ctx = context or {}
    ctx.setdefault("request", request)
    ctx.setdefault("current_query", request.query_params)
    return templates.TemplateResponse(request, template_name, ctx)
