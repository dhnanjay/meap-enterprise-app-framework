"""Correlation ID middleware (Section 46).

Every inbound request receives a correlation ID. Every derived log entry,
service operation, job, artifact, and exception should preserve it.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def _generate_correlation_id() -> str:
    return f"CORR-{uuid.uuid4().hex[:12].upper()}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or _generate_correlation_id()
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def get_correlation_id(request: Request) -> str:
    """Helper to extract correlation ID from request state."""
    return getattr(request.state, "correlation_id", "CORR-UNKNOWN")