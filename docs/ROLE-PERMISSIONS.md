# MEAP Role and Permission Operations

**Status:** configurable workspace-role release  
**Routes:** `/auth/admin/roles` and `/auth/admin/roles/{role_id}`  
**Audience:** workspace administrators and module developers

## Administrator workflow

Open **Roles** under Platform. The role list shows each role's type, effective registered-permission count, assigned-member count, and configuration link.

- Custom roles start with zero permissions and therefore grant nothing by default.
- Configure one role in a batch by checking the actions registered by each active module.
- A sensitive-administration verification is requested only when the current verification window has expired.
- Saving revokes active sessions for members assigned to that role. Their next sign-in resolves the new permission set.
- Every successful or failed role change is written to the workspace audit stream.

Role keys are stable machine identifiers. Renaming **Data Steward** changes its display name but does not change `data_steward` in assignments or audit history.

## Resolution order

MEAP resolves access in this order:

1. Expand the assigned role's stored grants only against permissions registered by active modules.
2. Apply explicit per-user `allow` overrides.
3. Apply explicit per-user `deny` overrides.
4. Use the resulting set for navigation filtering and route dependencies.

The Users application matrix currently changes only a module's registered view permission. The Roles panel changes the reusable action baseline.

## Built-in and custom roles

The built-in operational roles begin with documented wildcard patterns. This lets a newly registered module follow the generic default semantics. When an administrator saves one of those roles in the Roles panel, MEAP replaces the wildcards with the exact checked permission identifiers. From that point, newly introduced permissions require deliberate review and grant.

The `workspace_admin` role is different: it is fixed and continues to resolve every registered permission. It cannot be reduced, renamed, or customized through the UI or service.

Custom roles are workspace-scoped and exact by design. A role identifier from another workspace returns forbidden/not found and cannot be edited or assigned across the boundary.

## Module developer contract

Declare every capability in the module definition and enforce the identical constant at the route:

```python
VENDOR_IMPORT = "vendor_operations.vendor.import"

MODULE = ModuleDefinition(
    id="vendor_operations",
    name="Vendor Operations",
    route_prefix="/vendors",
    router=router,
    permissions=(VENDOR_VIEW, VENDOR_IMPORT),
    navigation=NavigationDefinition(
        label="Vendor Operations",
        group="Operations",
        required_permission=VENDOR_VIEW,
    ),
)

@router.post("/import")
def import_vendors(
    _permission=Depends(require_permission(VENDOR_IMPORT)),
):
    ...
```

The role editor discovers these permissions from the live registry. A database value cannot create a capability that is absent from the registry.

## Current boundary

- Role creation and permission editing are implemented; role deletion is intentionally withheld until reassignment and audit requirements are defined.
- A user has one effective workspace role in the current UI, although the schema can represent multiple assignments.
- Platform administration links—Users, Roles, Audit, and Developer—are fixed administrator capabilities, not module permissions.
- Changes are auditable database events, not cryptographically signed evidence.
