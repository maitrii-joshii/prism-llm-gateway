"""API routes for the Prism LLM Gateway."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from prism.api.responses import (
    build_streaming_headers,
    format_completion_response,
    set_context_headers,
)
from prism.services.chat_completion import ChatCompletionService
from prism.services.chat_streaming import StreamingCompletionService
from prism.services.metrics import metrics_registry
from prism.services.models.model import ModelService


# Root router contains operational and versioned API routes.
router = APIRouter()

# All public API endpoints automatically use /v1.
api_v1_router = APIRouter(prefix="/v1", tags=["API v1"])

_CONSOLE_HTML = (
    Path(__file__).resolve().parent.parent.parent
    / "console"
    / "index.html"
)


# -------------------------------------------------------------------
# Operational routes
# -------------------------------------------------------------------


@router.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Return application health status."""

    return {"status": "ok"}


@router.get("/", include_in_schema=False)
@router.get("/console", include_in_schema=False)
@router.get("/console/", include_in_schema=False)
async def route_ops_console():
    """Serve the operations console."""

    if _CONSOLE_HTML.is_file():
        return HTMLResponse(
            content=_CONSOLE_HTML.read_text(encoding="utf-8")
        )

    return HTMLResponse(
        content="<h1>console/index.html not found on disk</h1>",
        status_code=404,
    )


@router.get("/metrics", tags=["Observability"])
async def get_prometheus_metrics() -> Response:
    """Export Prometheus-compatible metrics."""

    metrics_text = metrics_registry.format_prometheus()

    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# -------------------------------------------------------------------
# Versioned public API routes
# -------------------------------------------------------------------


@api_v1_router.get("/models", tags=["Models"])
async def list_models(request: Request) -> JSONResponse:
    """Return available models and aliases."""

    loaded_config = getattr(
        request.app.state,
        "loaded_config",
        None,
    )

    models = ModelService.list_models(loaded_config)

    return JSONResponse(
        content={
            "object": "list",
            "data": models,
        }
    )


@api_v1_router.post("/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
    response: Response,
) -> Any:
    """Handle HTTP concerns and delegate request processing."""

    # Extract the API key from the supported HTTP headers.
    raw_api_key = request.headers.get("x-api-key")

    if not raw_api_key or not raw_api_key.strip():
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")

        if separator and scheme.lower() == "bearer" and token.strip():
            raw_api_key = token.strip()
        else:
            raw_api_key = None

    service = ChatCompletionService.from_app_state(
        request.app.state
    )

    result = await service.process(
        payload,
        request_id=request.state.request_id,
        raw_api_key=raw_api_key,
    )

    context = result.context

    if context.stream:
        headers = build_streaming_headers(context)

        streaming_service = StreamingCompletionService.from_app_state(
            request.app.state
        )

        streaming_body = streaming_service.create_body(
            result=result,
            raw_api_key=raw_api_key,
        )

        return StreamingResponse(
            streaming_body,
            status_code=200,
            media_type="text/event-stream",
            headers=headers,
        )

    # Non-streaming requests have already been logged by the service.
    set_context_headers(response, context)

    return format_completion_response(
        context.provider_response
    )


# Register versioned routes under the root router.
router.include_router(api_v1_router)
