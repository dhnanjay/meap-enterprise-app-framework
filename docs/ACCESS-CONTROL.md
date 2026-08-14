# MEAP Access Control

**Status:** first administrator-managed release  
**Scope:** generic workspace roles, per-user application access, navigation visibility, route enforcement, and workspace data isolation

## What the administrator can do

Open **Users** in the top bar. The page contains:

- The user and membership list.
- The invite form and generic starting role.
- An **Application visibility and access** matrix with one row per user and one column per registered application link.
- An **Enabled/Disabled** control for each user/application combination.

A change applies on the user's next request. Disabling an application does two things together:

1. Removes its link from the sidebar, dashboard, and application search.
2. Rejects a direct request to that application's protected routes with `403 Forbidden`.

The dashboard itself remains the authenticated workspace home. Users, Audit, and Developer are restricted workspace-administration capabilities and are not ordinary business-application links. Audit is deliberately a separate panel from Users so account administration stays focused while event history can use a dense list-report layout.

Open **Roles** under Platform to configure reusable action-level access. The role editor is generated from the active module registry, so adding or removing a registered permission changes the panel without maintaining a second hard-coded list. Custom roles start with no permissions. Built-in operational roles can be customized; the workspace-administrator role remains fixed with every registered permission.

## Generic starting roles

Roles are reusable permission bundles; they are not accounting job titles.

| Role | Intended use |
|---|---|
| Workspace administrator | Access, configuration, and all registered application permissions |
| Operator | Routine creation, execution, resolution, escalation, and flagging |
| Analyst | Read, create, execute, and flag without approval administration |
| Auditor | Read operational and audit information without mutation |
| Viewer | Read registered application views |

The access matrix adds an explicit per-user `allow` or `deny` override on top of the role. This makes a simple exception possible without creating a new role for one person.

## Developer contract for a navigation link

Every configurable module link must declare the permission that controls it:

```python
MODULE = ModuleDefinition(
    id="vendor_operations",
    name="Vendor Operations",
    route_prefix="/vendors",
    router=router,
    permissions=ALL_PERMISSIONS,
    navigation=NavigationDefinition(
        label="Vendor Operations",
        group="Operations",
        order=30,
        required_permission=VENDOR_VIEW,
    ),
)
```

Protect the corresponding routes with the same permission:

```python
@router.get("")
async def list_vendors(
    _permission=Depends(require_permission(VENDOR_VIEW)),
):
    ...
```

The registry will filter the link, but the route dependency is the security boundary. A review must reject a configurable link whose direct route is not protected.

## Data ownership contract

Authentication and link visibility are not sufficient for multi-user data safety. Business records carry `organization_id`, and repositories require an organization scope when they are created. Every identifier lookup, list, count, and mutation must include that scope.

```python
repository = VendorRepository(db, user.organization_id)
```

Never load a record globally and compare its organization afterward. Scope the database query itself so a foreign-workspace identifier behaves as not found.

## Persistence model

- `auth_access_roles`: workspace-scoped role definitions.
- `auth_role_permissions`: registered permission patterns belonging to a role.
- `auth_membership_roles`: role assignments for memberships.
- `auth_membership_permissions`: explicit per-user allow/deny overrides.
- Business module records: `organization_id` plus actor/timestamp fields where interaction state changes.

All role patterns are expanded only against permissions declared by the active module registry. A value in the database cannot invent an unregistered capability.

## Current boundary and next granularity

The Users matrix intentionally remains application-level **view** access for quick individual exceptions. The separate Roles panel configures the full registered action baseline—view, create, execute, resolve, approve, reject, and future module-defined actions—in one batch. Per-user allow/deny records are applied after the role baseline.

Recommended next steps:

1. Add custom-role retirement after safe member reassignment.
2. Add bulk user/role assignment with preview and confirmation.
3. Add periodic access-review reports and exportable audit evidence.
4. Validate role and session invalidation flows against PostgreSQL.

## Operational checks

- Test both link visibility and a direct URL request.
- Test the same record identifier from two workspaces.
- Confirm suspended memberships cannot create sessions.
- Confirm access changes create audit events.
- Keep the workspace administrator population small.
- Never treat a hidden button or link as authorization.
