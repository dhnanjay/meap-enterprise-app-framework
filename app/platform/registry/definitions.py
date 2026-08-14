"""Module Definitions and Registry Contracts (Sections 8, 9, 12).

Configuration determines what exists. Code determines how it works.
The registry is intentionally small — it holds identity and wiring metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter


@dataclass(frozen=True)
class NavigationDefinition:
    """A module's contribution to the shell navigation (Section 12).

    Modules declare navigation metadata; the Shell renders it.
    """

    label: str
    group: str = "General"
    order: int = 100
    icon: str | None = None
    required_permission: str | None = None


@dataclass(frozen=True)
class ModuleDefinition:
    """The typed contract every module implements (Section 8).

    A module definition says essentially:

        I exist.
        My name is X.
        My route is /x.
        Place me under group Y.
        These are my permissions.
        Mount this router.

    Nothing more. No business logic, no queries, no UI layout.
    """

    id: str
    name: str
    route_prefix: str
    router: APIRouter
    permissions: tuple[str, ...] = field(default_factory=tuple)
    navigation: NavigationDefinition | None = None
    icon: str | None = None
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True


@dataclass(frozen=True)
class RegisteredModule:
    """A module that has passed validation and is active in the registry."""

    definition: ModuleDefinition
    navigation_item: dict[str, Any] | None = None


class ModuleRegistryError(Exception):
    """Raised when module registration violates the contract."""


class DuplicateModuleError(ModuleRegistryError):
    """Two modules declared the same id or route_prefix."""


class ModuleContractError(ModuleRegistryError):
    """A module definition does not satisfy the contract."""
