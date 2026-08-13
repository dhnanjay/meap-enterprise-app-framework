"""MEAP Error Taxonomy (Sections 44, 45).

A small, bounded set of error categories. Do not create hundreds of
framework exception types.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone


class ErrorCategory(str, enum.Enum):
    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DOMAIN = "DOMAIN"
    DATA = "DATA"
    INTEGRATION = "INTEGRATION"
    JOB = "JOB"
    ARTIFACT = "ARTIFACT"
    SYSTEM = "SYSTEM"


class MeapError(Exception):
    """Base MEAP operational error with a traceable envelope (Section 45).

    Every operational error should be traceable through:
        error_id, correlation_id, module, operation, category, reason_code
    """

    category: ErrorCategory = ErrorCategory.SYSTEM
    http_status: int = 500

    def __init__(
        self,
        *,
        module: str,
        operation: str,
        reason_code: str,
        safe_message: str,
        category: ErrorCategory | None = None,
        correlation_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.error_id = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        self.module = module
        self.operation = operation
        self.reason_code = reason_code
        self.safe_message = safe_message
        self.correlation_id = correlation_id
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)
        if category is not None:
            self.category = category
        super().__init__(safe_message)

    def to_envelope(self) -> dict:
        """Return the structured error envelope for diagnostics/API responses."""
        return {
            "error_id": self.error_id,
            "correlation_id": self.correlation_id,
            "module": self.module,
            "operation": self.operation,
            "category": self.category.value,
            "reason_code": self.reason_code,
            "safe_message": self.safe_message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


# --- Common subclasses for convenience ----------------------------------


class ValidationError(MeapError):
    category = ErrorCategory.VALIDATION
    http_status = 422


class NotFoundError(MeapError):
    category = ErrorCategory.NOT_FOUND
    http_status = 404


class AuthorizationError(MeapError):
    category = ErrorCategory.AUTHORIZATION
    http_status = 403


class AuthenticationError(MeapError):
    category = ErrorCategory.AUTHENTICATION
    http_status = 401


class DataError(MeapError):
    category = ErrorCategory.DATA
    http_status = 422


class JobError(MeapError):
    category = ErrorCategory.JOB
    http_status = 500


class ArtifactError(MeapError):
    category = ErrorCategory.ARTIFACT
    http_status = 500