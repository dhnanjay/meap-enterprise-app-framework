"""Notebook permission vocabulary.

`platform.notebook.edit` grants the ability to execute arbitrary local code and
is therefore platform-admin-only. It must never be assignable by an
organization administrator.
"""

NOTEBOOK_VIEW = "platform.notebook.view"
NOTEBOOK_RUN = "platform.notebook.run"
NOTEBOOK_EDIT = "platform.notebook.edit"
NOTEBOOK_CREATE = "platform.notebook.create"
NOTEBOOK_PUBLISH = "platform.notebook.publish"
NOTEBOOK_EXPORT = "platform.notebook.export"
NOTEBOOK_MANAGE = "platform.notebook.manage"
NOTEBOOK_DATA_ACCESS = "platform.notebook.data_access"

ALL_PERMISSIONS = (
    NOTEBOOK_VIEW,
    NOTEBOOK_RUN,
    NOTEBOOK_EDIT,
    NOTEBOOK_CREATE,
    NOTEBOOK_PUBLISH,
    NOTEBOOK_EXPORT,
    NOTEBOOK_MANAGE,
    NOTEBOOK_DATA_ACCESS,
)

# Permissions an organization administrator may never grant.
PLATFORM_ADMIN_ONLY = frozenset({NOTEBOOK_EDIT})
