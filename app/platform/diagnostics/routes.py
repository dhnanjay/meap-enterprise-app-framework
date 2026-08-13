"""Developer Diagnostics area (Section 48).

Exposed at /developer in development and authorized diagnostic environments.
Provides visibility into modules, routes, configuration, and health.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.middleware.correlation import get_correlation_id
from app.platform.database.session import get_db
from app.platform.templates.rendering import render_page, render_fragment
from app.settings import get_settings

router = APIRouter(prefix="/developer", tags=["developer"])


@router.get("", response_class=HTMLResponse)
async def developer_home(request: Request):
    """Developer diagnostics dashboard."""
    settings = get_settings()
    registry = request.app.state.registry

    # Collect route information
    routes = []
    for route in request.app.routes:
        if hasattr(route, "methods") and route.methods:
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                routes.append(
                    {"path": route.path, "method": method, "name": route.name}
                )
        elif hasattr(route, "path"):
            routes.append({"path": route.path, "method": "MOUNT", "name": route.name})

    ctx = {
        "modules": registry.diagnostic_snapshot(),
        "permissions": sorted(registry.all_permissions),
        "navigation": registry.get_navigation(),
        "routes": sorted(routes, key=lambda r: (r["path"], r["method"])),
        "config": {
            "profile": settings.profile,
            "debug": settings.debug,
            "auth_enabled": settings.auth_enabled,
            "developer_area_enabled": settings.developer_area_enabled,
            "database_url": settings.database_url,
            "redis_url": settings.redis_url or "(not set — using local runner)",
            "artifact_storage_backend": settings.artifact_storage_backend,
        },
        "correlation_id": get_correlation_id(request),
    }
    return render_page(request, "developer/index.html", ctx)


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Lightweight health check for deployment probes."""
    checks = {"status": "healthy", "checks": {}}
    try:
        db.execute(text("SELECT 1"))
        checks["checks"]["database"] = "ok"
    except Exception as e:
        checks["checks"]["database"] = f"error: {e}"
        checks["status"] = "unhealthy"
    return JSONResponse(content=checks)


@router.get("/api/modules")
async def modules_api(request: Request):
    """JSON API for module diagnostics."""
    registry = request.app.state.registry
    return JSONResponse(
        content={
            "modules": registry.diagnostic_snapshot(),
            "permissions": sorted(registry.all_permissions),
        }
    )