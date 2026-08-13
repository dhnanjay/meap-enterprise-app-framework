"""Journal Entry Review — Module Definition (Sections 8, 9, 12, 70).

This is the single registration point. It says:

    I exist.
    My name is Journal Entry Review.
    My route is /je-review.
    Place me under Audit.
    These are my permissions.
    Mount this router.

Nothing more.
"""

from __future__ import annotations

from app.platform.registry.definitions import (
    ModuleDefinition,
    NavigationDefinition,
)

from app.modules.journal_entry_review.permissions import ALL_PERMISSIONS
from app.modules.journal_entry_review.routes import router

MODULE = ModuleDefinition(
    id="journal_entry_review",
    name="Journal Entry Review",
    route_prefix="/je-review",
    router=router,
    permissions=ALL_PERMISSIONS,
    navigation=NavigationDefinition(
        label="JE Review",
        group="Audit",
        order=30,
        icon="audit-activity",
    ),
    description="Journal entry risk analysis, review workflows, and approval tracking.",
    version="1.0.0",
    enabled=True,
)