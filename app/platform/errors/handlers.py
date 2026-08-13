"""Global exception handlers — convert MeapError into responses (Section 45).

For HTMX requests, return an error fragment.
For normal requests, return a full error page or JSON.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.platform.errors.taxonomy import MeapError


def _error_status_class(exc: MeapError) -> str:
    """Map the framework taxonomy onto the five UI status semantics."""
    category = exc.category.value
    if category in {"INTEGRATION", "JOB", "SYSTEM", "ARTIFACT"}:
        return "meap-badge--critical"
    if category in {"VALIDATION", "DOMAIN", "DATA", "CONFLICT"}:
        return "meap-badge--attention"
    return ""


async def meap_error_handler(request: Request, exc: MeapError) -> HTMLResponse | JSONResponse:
    """Handle known MEAP errors with structured envelopes."""
    is_htmx = request.headers.get("HX-Request") == "true"

    if exc.correlation_id is None:
        exc.correlation_id = getattr(request.state, "correlation_id", None)

    if is_htmx:
        return HTMLResponse(
            content=_render_error_fragment(exc),
            status_code=exc.http_status,
            headers={"HX-Retarget": "#meap-error-region", "HX-Reswap": "innerHTML"},
        )

    accept = request.headers.get("accept", "")
    if "application/json" in accept or "text/html" not in accept:
        return JSONResponse(content=exc.to_envelope(), status_code=exc.http_status)

    return HTMLResponse(content=_render_error_page(exc), status_code=exc.http_status)


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        content={
            "error_id": "ERR-UNEXPECTED",
            "correlation_id": correlation_id,
            "category": "SYSTEM",
            "safe_message": "An unexpected error occurred.",
            "detail": str(exc) if request.app.state.settings.debug else None,
        },
        status_code=500,
    )


def _render_error_fragment(exc: MeapError) -> str:
    status_class = _error_status_class(exc)
    return f"""
    <div class="meap-error-fragment" role="alert">
      <div class="meap-error-code">Error: {exc.error_id}</div>
      <div class="meap-error-message">{exc.safe_message}</div>
      <div class="meap-error-meta">
        <span class="meap-badge {status_class}">{exc.category.value}</span>
        <span class="meap-badge">{exc.reason_code}</span>
      </div>
    </div>
    """


def _render_error_page(exc: MeapError) -> str:
    status_class = _error_status_class(exc)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Error {exc.error_id} — MEAP</title>
  <link rel="stylesheet" href="/static/css/meap.css">
</head>
<body class="meap-error-page">
  <div class="meap-error-container">
    <h1>Something went wrong</h1>
    <div class="meap-error-code">Error: {exc.error_id}</div>
    <p class="meap-error-message">{exc.safe_message}</p>
    <div class="meap-error-meta">
      <span class="meap-badge {status_class}">{exc.category.value}</span>
      <span class="meap-badge">{exc.reason_code}</span>
      <span class="meap-badge">Module: {exc.module}</span>
      <span class="meap-badge">Operation: {exc.operation}</span>
    </div>
    <p><a href="/">Return to dashboard</a></p>
  </div>
</body>
</html>"""
