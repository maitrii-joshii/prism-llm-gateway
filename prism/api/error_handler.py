"""Centralized error handling for the Prism LLM Gateway.

Provides OpenAI-compatible error responses for domain exceptions
and unexpected server errors while ensuring request IDs are included
and internal exception details are not exposed to clients.
"""

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from prism.domain.errors import (
    BudgetExceededError,
    PrismError,
    RateLimitError,
    UpstreamError,
)


logger = logging.getLogger(__name__)

GENERIC_INTERNAL_ERROR = "An unexpected error occurred."
GENERIC_UPSTREAM_ERROR = "The upstream provider request failed."


def get_request_id(request: Request) -> str:
    """Get the existing request ID or generate one if unavailable."""

    request_id = getattr(request.state, "request_id", None)

    if not request_id:
        request_id = request.headers.get("x-prism-request-id")

    if not request_id:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id

    return request_id


async def prism_error_handler(
    request: Request,
    exc: PrismError,
) -> JSONResponse:
    """Convert domain errors into safe OpenAI-compatible JSON responses.

    For rate-limit (429) and budget-exceeded (429) errors a ``Retry-After``
    header is included so OpenAI-compatible client SDKs know how long to wait
    before retrying.  The value of 60 seconds is a conservative safe default;
    the real reset window depends on the tenant's RPM configuration.
    """

    status_code = getattr(exc, "status_code", 500)
    error_type = getattr(exc, "error_type", "internal_error")
    request_id = get_request_id(request)

    # Never expose internal provider error details to API clients.
    if isinstance(exc, UpstreamError):
        message = GENERIC_UPSTREAM_ERROR
    else:
        message = str(exc)

    response_headers: dict[str, str] = {
        "x-prism-request-id": request_id,
    }

    # Add Retry-After on throttle responses so clients back off correctly.
    if isinstance(exc, (RateLimitError, BudgetExceededError)):
        response_headers["Retry-After"] = "60"

    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "code": status_code,
            }
        },
    )


async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions without exposing internal details."""

    request_id = get_request_id(request)

    logger.exception(
        "Unhandled exception while processing request_id=%s",
        request_id,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return JSONResponse(
        status_code=500,
        headers={
            "x-prism-request-id": request_id,
        },
        content={
            "error": {
                "message": GENERIC_INTERNAL_ERROR,
                "type": "internal_error",
                "code": 500,
            }
        },
    )
