"""OpenAI-compatible response formatting and Prism response headers."""

import time
from typing import Any
from uuid import uuid4

from fastapi import Response

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse, RequestContext


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
        context.cost_usd,
        "g",
    )


def build_streaming_headers(
    context: RequestContext,
) -> dict[str, str]:
    """Build response headers before streaming starts."""
    if context.cache_status != "hit":
        if not context.provider_name or not context.model_resolved:
            raise UpstreamError(
                "Provider and model must be resolved before streaming."
            )

    headers = {
        "x-prism-request-id": context.request_id,
        "x-prism-cache": context.cache_status,
        "x-prism-fallback": str(context.fallback_used).lower(),
        "x-prism-cost-usd": format(context.cost_usd, "g"),
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if context.provider_name and context.model_resolved:
        headers["x-prism-provider"] = (
            f"{context.provider_name}/{context.model_resolved}"
        )

    return headers