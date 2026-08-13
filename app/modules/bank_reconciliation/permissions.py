"""Bank Reconciliation — Permissions (Section 41).

Permission names follow: module.resource.action
"""

BANK_RECON_VIEW = "bank_reconciliation.reconciliation.view"
BANK_RECON_CREATE = "bank_reconciliation.reconciliation.create"
BANK_RECON_EXECUTE = "bank_reconciliation.reconciliation.execute"
BANK_RECON_RESOLVE = "bank_reconciliation.exception.resolve"
BANK_RECON_ESCALATE = "bank_reconciliation.exception.escalate"

ALL_PERMISSIONS: tuple[str, ...] = (
    BANK_RECON_VIEW,
    BANK_RECON_CREATE,
    BANK_RECON_EXECUTE,
    BANK_RECON_RESOLVE,
    BANK_RECON_ESCALATE,
)