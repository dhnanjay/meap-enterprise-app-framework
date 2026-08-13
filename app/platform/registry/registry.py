"""Module Registry — deterministic registration, validation, navigation (Section 9).

Registration must be deterministic.
There shall be no filesystem magic.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from app.platform.registry.definitions import (
    DuplicateModuleError,
    ModuleContractError,
    ModuleDefinition,
    NavigationDefinition,
    RegisteredModule,
)

logger = structlog.get_logger()


class ModuleRegistry:
    """The central registry of all active modules.

    Built once at startup from an explicit MODULES list.
    """

    def __init__(self) -> None:
        self._modules: dict[str, RegisteredModule] = {}
        self._permissions: set[str] = set()
        self._routers_mounted: bool = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, definition: ModuleDefinition) -> None:
        """Validate and register a single module definition."""

        self._validate(definition)

        if not definition.enabled:
            logger.info(
                "module.registered_disabled",
                module_id=definition.id,
                name=definition.name,
            )
            return

        nav_item = self._build_navigation_item(definition)

        registered = RegisteredModule(
            definition=definition,
            navigation_item=nav_item,
        )
        self._modules[definition.id] = registered

        for perm in definition.permissions:
            if perm in self._permissions:
                raise DuplicateModuleError(
                    f"Permission '{perm}' is declared by multiple modules"
                )
            self._permissions.add(perm)

        logger.info(
            "module.registered",
            module_id=definition.id,
            name=definition.name,
            route_prefix=definition.route_prefix,
            permissions=list(definition.permissions),
        )

    def _validate(self, d: ModuleDefinition) -> None:
        """Enforce the module contract (Section 8)."""

        if not d.id or not d.id.replace("_", "").isalnum():
            raise ModuleContractError(
                f"Module id must be snake_case alphanumeric: {d.id!r}"
            )
        if not d.name.strip():
            raise ModuleContractError(f"Module name is empty for id={d.id!r}")
        if not d.route_prefix.startswith("/"):
            raise ModuleContractError(
                f"Module route_prefix must start with '/': {d.route_prefix!r}"
            )
        if d.id in self._modules:
            raise DuplicateModuleError(f"Module id already registered: {d.id}")
        for existing in self._modules.values():
            if existing.definition.route_prefix == d.route_prefix:
                raise DuplicateModuleError(
                    f"Route prefix '{d.route_prefix}' already used by "
                    f"module '{existing.definition.id}'"
                )

    def _build_navigation_item(self, d: ModuleDefinition) -> dict[str, Any] | None:
        nav = d.navigation
        if nav is None:
            return None
        return {
            "module_id": d.id,
            "label": nav.label,
            "group": nav.group,
            "order": nav.order,
            "icon": nav.icon or d.icon,
            "href": d.route_prefix,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def modules(self) -> dict[str, RegisteredModule]:
        return dict(self._modules)

    def get(self, module_id: str) -> RegisteredModule | None:
        return self._modules.get(module_id)

    @property
    def all_permissions(self) -> frozenset[str]:
        return frozenset(self._permissions)

    def has_permission(self, permission: str) -> bool:
        """Return True only for registered permissions (Section 41).

        If auth is disabled, callers may bypass checks, but the permission
        must still exist in the registry — this keeps the contract honest.
        """
        return permission in self._permissions

    # ------------------------------------------------------------------
    # Navigation model (Section 12)
    # ------------------------------------------------------------------

    def get_navigation(self) -> list[dict[str, Any]]:
        """Return navigation items grouped and ordered for shell rendering.

        Returns a list of groups:
            [{"group": "Accounting", "items": [...]}, ...]
        """
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for mod in self._modules.values():
            if mod.navigation_item:
                groups[mod.navigation_item["group"]].append(mod.navigation_item)

        result = []
        for group_name, items in sorted(groups.items()):
            items.sort(key=lambda i: (i["order"], i["label"]))
            result.append({"group": group_name, "items": items})
        return result

    # ------------------------------------------------------------------
    # Diagnostics (Section 48)
    # ------------------------------------------------------------------

    def diagnostic_snapshot(self) -> list[dict[str, Any]]:
        """Return a flat diagnostic view of all registered modules."""
        return [
            {
                "id": mod.definition.id,
                "name": mod.definition.name,
                "route_prefix": mod.definition.route_prefix,
                "enabled": mod.definition.enabled,
                "permissions": list(mod.definition.permissions),
                "has_navigation": mod.navigation_item is not None,
                "version": mod.definition.version,
            }
            for mod in sorted(self._modules.values(), key=lambda m: m.definition.id)
        ]


def build_registry(definitions: list[ModuleDefinition]) -> ModuleRegistry:
    """Construct a registry from an explicit list (Section 9).

    Preferred registration is explicit:
        MODULES = [BankReconciliationModule, ...]
    """
    registry = ModuleRegistry()
    for definition in definitions:
        registry.register(definition)
    logger.info(
        "registry.built",
        module_count=len(registry.modules),
        permission_count=len(registry.all_permissions),
    )
    return registry