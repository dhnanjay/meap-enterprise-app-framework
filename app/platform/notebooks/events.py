"""Stable notebook audit-event vocabulary."""

NOTEBOOK_REGISTERED = "notebook.registered"
NOTEBOOK_UPDATED = "notebook.updated"
NOTEBOOK_ENABLED = "notebook.enabled"
NOTEBOOK_DISABLED = "notebook.disabled"
NOTEBOOK_LAUNCHED = "notebook.launched"
NOTEBOOK_RUNTIME_STARTED = "notebook.runtime_started"
NOTEBOOK_RUNTIME_STOPPED = "notebook.runtime_stopped"
NOTEBOOK_EXPORTED = "notebook.exported"
NOTEBOOK_ARTIFACT_PUBLISHED = "notebook.artifact_published"
NOTEBOOK_ACCESS_DENIED = "notebook.access_denied"

ALL_EVENTS = (
    NOTEBOOK_REGISTERED,
    NOTEBOOK_UPDATED,
    NOTEBOOK_ENABLED,
    NOTEBOOK_DISABLED,
    NOTEBOOK_LAUNCHED,
    NOTEBOOK_RUNTIME_STARTED,
    NOTEBOOK_RUNTIME_STOPPED,
    NOTEBOOK_EXPORTED,
    NOTEBOOK_ARTIFACT_PUBLISHED,
    NOTEBOOK_ACCESS_DENIED,
)
