"""Application entry point for Prism LLM Gateway."""

import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.config.logging import (
    configure_logging,
    get_logger,
    get_uvicorn_logging_config,
)
from prism.domain.errors import PrismError


logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the Prism FastAPI application."""

    configure_logging()

    app = FastAPI(
        title="Prism LLM Gateway",
        version="0.1.0",
    )

    # Register request ID and structured logging middleware.
    app.middleware("http")(request_id_middleware)

    # Register API routes.
    app.include_router(router)

    @app.exception_handler(PrismError)
    async def prism_error_handler(
        request: Request,
        exc: PrismError,
    ) -> JSONResponse:
        """Convert Prism errors into structured JSON responses."""

        logger.error(
            "Prism request failed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "error_type": exc.error_type,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "type": exc.error_type,
                    "code": exc.status_code,
                }
            },
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return the gateway health status."""

        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    """Start the Prism HTTP server."""

    port = int(os.getenv("PORT", "3000"))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False,
        log_config=get_uvicorn_logging_config(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
