"""API routes for the Prism LLM Gateway."""

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from prism.config.logging import get_logger
from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse, RequestContext
from prism.ports.provider import ProviderAdapter

router = APIRouter()
logger = get_logger(__name__)


def get_provider_adapter(request: Request) -> ProviderAdapter:
    """Retrieve the provider adapter configured on the FastAPI app."""

    adapter = getattr(request.app.state, "provider_adapter", None)

    if adapter is None:
        raise UpstreamError("Provider adapter is not configured")

    return adapter


def invalid_request(message: str) -> JSONResponse:
    """Build an OpenAI-compatible HTTP 400 response."""

    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": 400,
            }
        },
    )


def format_completion_response(
    result: ProviderResponse,
) -> dict[str, Any]:
    """Convert the normalized provider response to OpenAI's format."""

    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.content,
                },
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        },
    }


def set_context_headers(
    response: Response,
    context: RequestContext,
) -> None:
    """Set Prism response headers using the completed request context."""

    response.headers["x-prism-request-id"] = context.request_id

    if context.provider_name and context.model_resolved:
        response.headers["x-prism-provider"] = (
            f"{context.provider_name}/{context.model_resolved}"
        )

    response.headers["x-prism-cache"] = context.cache_status
    response.headers["x-prism-fallback"] = str(
        context.fallback_used
    ).lower()
    response.headers["x-prism-cost-usd"] = format(
        context.cost_usd, "g"
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
    response: Response,
) -> Any:
    """Validate a chat request, call the provider, and set response headers."""

    model = payload.get("model")
    messages = payload.get("messages")
    stream = payload.get("stream", False)

    if not isinstance(model, str) or not model.strip():
        logger.warning(
            "Invalid chat completion request",
            extra={
                "path": "/v1/chat/completions",
                "error_type": "InvalidModel",
            },
        )
        return invalid_request(
            "'model' is required and must be a non-empty string"
        )

    if not isinstance(messages, list) or not messages:
        logger.warning(
            "Invalid chat completion request",
            extra={
                "path": "/v1/chat/completions",
                "model": model,
                "error_type": "InvalidMessages",
            },
        )
        return invalid_request(
            "'messages' is required and must be a non-empty list"
        )

    if not all(isinstance(message, dict) for message in messages):
        logger.warning(
            "Invalid chat completion request",
            extra={
                "path": "/v1/chat/completions",
                "model": model,
                "error_type": "InvalidMessages",
            },
        )
        return invalid_request(
            "'messages' must contain JSON objects"
        )

    if not isinstance(stream, bool):
        logger.warning(
            "Invalid chat completion request",
            extra={
                "path": "/v1/chat/completions",
                "model": model,
                "error_type": "InvalidStream",
            },
        )
        return invalid_request("'stream' must be a boolean")

    adapter = get_provider_adapter(request)

    # Prototype only: use the first configured seed key to populate
    # context metadata. This does NOT authenticate the incoming caller.
    config = getattr(request.app.state, "config", None)
    seed_keys = getattr(config, "seed_keys", None)

    if not seed_keys:
        raise UpstreamError(
            "Seed key configuration is not available"
        )

    clock = getattr(request.app.state, "clock", None)

    if clock is None:
        raise UpstreamError("Clock is not configured")

    context = RequestContext(
        request_id=request.state.request_id,
        key_config=seed_keys[0],
        model_requested=model,
        messages=messages,
        stream=stream,
        start_time=clock.now(),
        provider_name="alpha",
        decision_trace=["request validation ok"],
    )

    # Record the provider selected by the current prototype flow.
    context.decision_trace.append("provider alpha selected")

    logger.info(
        "Forwarding request to provider",
        extra={
            "path": "/v1/chat/completions",
            "model": model,
        },
    )

    # Call the provider using the existing pass-through flow.
    result = await adapter.complete(payload)

    # Record the model reported by the provider.
    context.model_resolved = result.model
    context.decision_trace.append(
        f"{result.model} response received"
    )

    # Add response metadata from the context after the provider succeeds.
    set_context_headers(response, context)

    logger.info(
        "Provider response received",
        extra={
            "path": "/v1/chat/completions",
            "model": result.model,
        },
    )

    # Prepare the response body before logging the final decision trace.
    completion_response = format_completion_response(result)

    logger.info(
        "Decision trace: %s",
        " → ".join(context.decision_trace),
        extra={
            "path": "/v1/chat/completions",
            "model": result.model,
        },
    )

    return completion_response
