"""Journal Entry Review — Permissions (Section 41).

Permission names follow: module.resource.action
"""

JE_REVIEW_VIEW = "journal_entry_review.review.view"
JE_REVIEW_CREATE = "journal_entry_review.review.create"
JE_REVIEW_FLAG = "journal_entry_review.entry.flag"
JE_REVIEW_APPROVE = "journal_entry_review.entry.approve"
JE_REVIEW_REJECT = "journal_entry_review.entry.reject"

ALL_PERMISSIONS: tuple[str, ...] = (
    JE_REVIEW_VIEW,
    JE_REVIEW_CREATE,
    JE_REVIEW_FLAG,
    JE_REVIEW_APPROVE,
    JE_REVIEW_REJECT,
)