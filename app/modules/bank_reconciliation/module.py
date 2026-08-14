"""Bank Reconciliation — Module Definition (Sections 8, 9, 12, 70).

This is the single registration point. It says:

    I exist.
    My name is Bank Reconciliation.
    My route is /bank-recon.
    Place me under Accounting.
    These are my permissions.
    Mount this router.

Nothing more.
"""

from __future__ import annotations

from app.platform.registry.definitions import (
    ModuleDefinition,
    NavigationDefinition,
)

from app.modules.bank_reconciliation.permissions import ALL_PERMISSIONS, BANK_RECON_VIEW
from app.modules.bank_reconciliation.routes import router

MODULE = ModuleDefinition(
    id="bank_reconciliation",
    name="Bank Reconciliation",
    route_prefix="/bank-recon",
    router=router,
    permissions=ALL_PERMISSIONS,
    navigation=NavigationDefinition(
        label="Bank Reconciliation",
        group="Accounting",
        order=20,
        icon="compare-arrows",
        required_permission=BANK_RECON_VIEW,
    ),
    description="Bank statement reconciliation, exception management, and review workflows.",
    version="1.0.0",
    enabled=True,
)
