import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.ports.provider import ProviderAdapter

router = APIRouter()


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


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
) -> Any:
    """Validate a chat request and forward it to the provider."""

    model = payload.get("model")
    messages = payload.get("messages")

    if not isinstance(model, str) or not model.strip():
        return invalid_request(
            "'model' is required and must be a non-empty string"
        )

    if not isinstance(messages, list) or not messages:
        return invalid_request(
            "'messages' is required and must be a non-empty list"
        )

    adapter = get_provider_adapter(request)

    # No pipeline stages yet: forward the validated request directly.
    result = await adapter.complete(payload)

    return format_completion_response(result)
