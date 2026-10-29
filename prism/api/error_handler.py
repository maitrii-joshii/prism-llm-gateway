from fastapi import Request
from fastapi.responses import JSONResponse

from prism.domain.errors import PrismError


async def prism_error_handler(
    request: Request,
    exc: PrismError,
) -> JSONResponse:
    """Convert domain errors into OpenAI-compatible JSON responses."""

    status_code = getattr(exc, "status_code", 500)
    error_type = getattr(exc, "error_type", "internal_error")

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": str(exc),
                "type": error_type,
                "code": status_code,
            }
        },
    )
