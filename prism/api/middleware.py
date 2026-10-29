"""HTTP middleware for request IDs and structured logging."""

from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.responses import Response

from prism.config.logging import (
    get_logger,
    reset_request_id,
    set_request_id,
)

logger = get_logger(__name__)


async def request_id_middleware(
    request: Request,
    call_next,
) -> Response:
    """Assign a request ID and log the request lifecycle."""

    request_id = f"req_{uuid4().hex[:12]}"
    request.state.request_id = request_id

    context_token = set_request_id(request_id)
    started_at = perf_counter()

    try:
        logger.info(
            "Request received",
            extra={
                "method": request.method,
                "path": request.url.path,
            },
        )

        response = await call_next(request)

        duration_ms = round((perf_counter() - started_at) * 1000, 2)

        log_method = (
            logger.error
            if response.status_code >= 500
            else logger.warning
            if response.status_code >= 400
            else logger.info
        )

        log_method(
            "Response sent",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["x-prism-request-id"] = request_id
        return response

    except Exception as exc:
        logger.error(
            "Request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
            },
        )
        raise

    finally:
        reset_request_id(context_token)
