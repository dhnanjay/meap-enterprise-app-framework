"""MEAP Application Entry Point (Sections 9, 11, 17, 40, 46, 48).

Startup performs:
    Load settings → Initialize platform → Discover modules → Validate →
    Register routes → Register permissions → Build navigation → Start.

Registration is explicit and deterministic (Section 9).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.authentication import AuthenticationMiddleware
from app.modules.bank_reconciliation.module import MODULE as BankReconciliationModule
from app.modules.journal_entry_review.module import MODULE as JournalEntryReviewModule
from app.platform.database import base as db_base
from app.platform.audit import models as _audit_models  # noqa: F401
from app.platform.notebooks import models as _notebook_models  # noqa: F401
from app.platform.auth import models as _auth_models  # noqa: F401
from app.platform.auth.routes import router as auth_router
from app.platform.database.session import init_session_factory
from app.platform.diagnostics.routes import router as diagnostics_router
from app.platform.errors.handlers import (
    generic_error_handler,
    meap_error_handler,
)
from app.platform.errors.taxonomy import MeapError
from app.platform.registry.definitions import ModuleDefinition
from app.platform.registry.registry import build_registry
from app.platform.templates.rendering import render_page
from app.settings import get_settings

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
)

logger = structlog.get_logger()

# ──────────────────────────────────────────────────────────────────────────
# EXPLICIT MODULE LIST (Section 9)
#
# This is the single place that answers:
#   "Which modules exist in this application?"
#
# To add a module: import its MODULE definition and add it here.
# To remove a module: delete its import and line here.
# To disable a module temporarily: set enabled=False in its module.py.
# ──────────────────────────────────────────────────────────────────────────
MODULES: list[ModuleDefinition] = [
    BankReconciliationModule,
    JournalEntryReviewModule,
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    app.state.settings = settings

    if settings.profile == "production" and settings.auth_enabled:
        insecure_values = (
            settings.session_hmac_key.startswith("local-"),
            settings.token_hmac_key.startswith("local-"),
            settings.credential_encryption_key_id.startswith("local-"),
            not settings.credential_encryption_keys
            and settings.credential_encryption_key
            == "4G9HkM4pV4C2u_uMaY-7z8s8Q-OHN34JOj0H6jOO1V0=",
        )
        if any(insecure_values):
            raise RuntimeError("Production authentication keys must be explicitly configured")

    # --- Database (Section 43) ---
    # Use module-qualified calls so test conftest can patch db_base.make_engine
    engine = db_base.make_engine(settings.database_url)
    session_factory = db_base.make_session_factory(engine)
    init_session_factory(session_factory)
    app.state.engine = engine

    # Create tables (for local/dev — production uses Alembic migrations)
    if settings.profile in ("local", "development", "test"):
        db_base.Base.metadata.create_all(bind=engine)
        logger.info("database.tables_created", profile=settings.profile)

    # --- Module Registry (Section 9) ---
    registry = build_registry(MODULES)
    app.state.registry = registry

    # --- Mount module routers ---
    # Note: Module routers already carry their own prefix (e.g. "/bank-recon")
    # so we mount them WITHOUT an additional prefix here (Section 9).
    for mod in registry.modules.values():
        app.include_router(mod.definition.router)

    # --- Diagnostics (Section 48) ---
    if settings.developer_area_enabled:
        app.include_router(diagnostics_router)
        logger.info("diagnostics.enabled", path="/developer")

    logger.info(
        "meap.started",
        profile=settings.profile,
        modules=list(registry.modules.keys()),
        auth_enabled=settings.auth_enabled,
    )
    yield

    # --- Shutdown ---
    engine.dispose()
    logger.info("meap.stopped")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Modular Enterprise Application Platform",
        version="1.0.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    # --- Middleware (Section 46) ---
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(AuthenticationMiddleware)

    # Authentication is platform infrastructure, not a business module.
    app.include_router(auth_router)

    # --- Static files (Section 22) ---
    static_dir = Path(__file__).parent / "platform" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # --- Error handlers (Section 45) ---
    app.add_exception_handler(MeapError, meap_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    # --- Dashboard / Home route ---
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Platform dashboard showing registered modules and navigation."""
        registry = request.app.state.registry
        ctx = {
            "modules": registry.diagnostic_snapshot(),
        }
        return render_page(request, "dashboard.html", ctx)

    @app.get("/search")
    async def global_search(request: Request, q: str = ""):
        """Global search entry point (owned by Platform)."""
        registry = request.app.state.registry
        results: list[dict] = []
        # Modules can expose search providers in the future.
        # For now, search module names and descriptions.
        if q:
            qlower = q.lower()
            for mod in registry.modules.values():
                d = mod.definition
                if qlower in d.name.lower() or qlower in d.description.lower():
                    results.append({
                        "label": d.name,
                        "href": d.route_prefix,
                        "description": d.description,
                    })
        ctx = {"query": q, "results": results}
        return render_page(request, "search_results.html", ctx)

    return app


app = create_app()
