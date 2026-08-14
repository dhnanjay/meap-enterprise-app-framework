"""Generic default role bundles and permission-pattern expansion."""

from __future__ import annotations

from fnmatch import fnmatchcase


DEFAULT_ROLE_BUNDLES: dict[str, dict[str, object]] = {
    "workspace_admin": {
        "display_name": "Workspace administrator",
        "description": "Manages workspace access, configuration, and all operational capabilities.",
        "patterns": ("*",),
    },
    "operator": {
        "display_name": "Operator",
        "description": "Creates, updates, imports, executes, and resolves operational work.",
        "patterns": ("*.view", "*.create", "*.execute", "*.resolve", "*.escalate", "*.flag"),
    },
    "analyst": {
        "display_name": "Analyst",
        "description": "Reads data and performs analysis without approval or access administration.",
        "patterns": ("*.view", "*.create", "*.execute", "*.flag"),
    },
    "auditor": {
        "display_name": "Auditor",
        "description": "Reads operational data, evidence, and audit information without mutation.",
        "patterns": ("*.view", "audit.*.read", "audit.read"),
    },
    "viewer": {
        "display_name": "Viewer",
        "description": "Reads explicitly registered module resources.",
        "patterns": ("*.view",),
    },
}


def expand_permission_patterns(
    patterns: set[str] | frozenset[str], registered_permissions: set[str] | frozenset[str]
) -> frozenset[str]:
    """Resolve persisted glob patterns only against registered permissions."""
    return frozenset(
        permission
        for permission in registered_permissions
        if any(fnmatchcase(permission, pattern) for pattern in patterns)
    )
