"""API routes for the Prism LLM Gateway."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from prism.config.logging import get_logger
from prism.domain.cost import CostCalculator
from prism.domain.errors import InvalidRequestError, UpstreamError
from prism.domain.models import ProviderResponse, RequestContext
from prism.ports.provider import ProviderAdapter
from prism.services.pipeline import Pipeline
from prism.services.streaming import stream_response
from prism.services.stages.auth import authenticate_request
from prism.services.stages.allowlist import enforce_model_allowlist
from prism.services.stages.budget import enforce_budget
from prism.services.stages.rate_limiter import enforce_rate_limit
from prism.services.stages.validate import validate_request

router = APIRouter()
logger = get_logger(__name__)


def get_provider_adapter(request: Request) -> ProviderAdapter:
    """Retrieve the provider adapter configured on the FastAPI app."""

    adapter = getattr(request.app.state, "provider_adapter", None)

    if adapter is None:
        raise UpstreamError("Provider adapter is not configured")

    return adapter


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


def build_streaming_headers(
    context: RequestContext,
) -> dict[str, str]:
    """Build response headers before streaming starts."""

    if not context.provider_name or not context.model_resolved:
        raise UpstreamError(
            "Provider and model must be resolved before streaming."
        )

    return {
        "x-prism-request-id": context.request_id,
        "x-prism-provider": (
            f"{context.provider_name}/{context.model_resolved}"
        ),
        "x-prism-cache": "miss",
        "x-prism-fallback": str(context.fallback_used).lower(),
        # Final cost is not known until the provider sends usage.
        "x-prism-cost-usd": "0",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }


async def format_streaming_body(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
    usage_repository: Any,
    loaded_config: Any,
    adapter: Any,
) -> AsyncIterator[str]:
    """Forward SSE chunks and format the final OpenAI DONE marker."""

    streaming_generator = stream_response(
        provider_stream=provider_stream,
        context=context,
        usage_repository=usage_repository,
        loaded_config=loaded_config,
        adapter=adapter,
    )

    try:
        async for formatted_chunk in streaming_generator:
            # stream_response represents completion internally as
            # data: {"done": true}\n\n.
            try:
                data = formatted_chunk.removeprefix("data: ").strip()
                event = json.loads(data)

                if event.get("done") is True:
                    yield "data: [DONE]\n\n"
                    # Continue iteration so the underlying generator
                    # reaches its normal completion and executes finally.
                    continue

            except (json.JSONDecodeError, AttributeError):
                pass

            # Forward each chunk immediately.
            yield formatted_chunk

    finally:
        # Ensure the underlying generator is closed if the client
        # disconnects or the response generator is cancelled.
        await streaming_generator.aclose()


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
    response: Response,
) -> Any:
    """Process a chat completion request through the pipeline."""

    key_repository = getattr(
        request.app.state,
        "key_repository",
        None,
    )

    if key_repository is None:
        raise UpstreamError("Key repository is not configured")

    clock = getattr(request.app.state, "clock", None)

    if clock is None:
        raise UpstreamError("Clock is not configured")

    rate_limiter = getattr(
        request.app.state,
        "rate_limiter",
        None,
    )

    if rate_limiter is None:
        raise UpstreamError("Rate limiter is not configured")

    usage_repository = getattr(
        request.app.state,
        "usage_repository",
        None,
    )

    if usage_repository is None:
        raise UpstreamError("Usage repository is not configured")

    initial_model = payload.get("model", "")
    initial_messages = payload.get("messages", [])

    context = RequestContext(
        request_id=request.state.request_id,
        model_requested=(
            initial_model if isinstance(initial_model, str) else ""
        ),
        messages=(
            initial_messages
            if isinstance(initial_messages, list)
            else []
        ),
        stream=False,
        request_payload=payload.copy(),
        start_time=clock.now(),
    )

    async def auth_stage(
        context: RequestContext,
    ) -> RequestContext:
        await authenticate_request(
            request,
            context,
            key_repository,
        )
        return context

    async def validate_stage(
        context: RequestContext,
    ) -> RequestContext:
        validated_payload = validate_request(
            context.request_payload
        )

        stream = validated_payload.get("stream", False)

        if not isinstance(stream, bool):
            raise InvalidRequestError(
                "'stream' must be a boolean."
            )

        context.request_payload = validated_payload
        context.model_requested = validated_payload["model"]
        context.messages = validated_payload["messages"]
        context.stream = stream

        context.decision_trace.append("request validation ok")

        return context

    async def rate_limit_stage(
        context: RequestContext,
    ) -> RequestContext:
        return await enforce_rate_limit(
            context,
            rate_limiter,
        )

    async def allowlist_stage(
        context: RequestContext,
    ) -> RequestContext:
        return await enforce_model_allowlist(context)

    async def budget_stage(
        context: RequestContext,
    ) -> RequestContext:
        return await enforce_budget(
            context,
            usage_repository,
        )

    async def provider_call_stage(
        context: RequestContext,
    ) -> RequestContext:
        loaded_config = getattr(
            request.app.state,
            "loaded_config",
            None,
        )

        if loaded_config is None:
            raise UpstreamError(
                "Gateway configuration is not loaded"
            )

        adapter = get_provider_adapter(request)

        # Provider selection must happen before response headers are sent.
        context.provider_name = "alpha"

        if context.stream:
            context.model_resolved = context.model_requested

            context.decision_trace.append(
                "streaming provider alpha selected"
            )

            logger.info(
                "Starting provider streaming request",
                extra={
                    "path": "/v1/chat/completions",
                    "model": context.model_requested,
                },
            )

            # The provider stream is consumed after the pipeline finishes.
            return context

        context.decision_trace.append("provider alpha selected")

        logger.info(
            "Forwarding request to provider",
            extra={
                "path": "/v1/chat/completions",
                "model": context.model_requested,
            },
        )

        result = await adapter.complete(
            context.request_payload
        )

        context.provider_response = result
        context.model_resolved = result.model

        context.decision_trace.append(
            f"{result.model} response received"
        )

        pricing = loaded_config.model_pricing.get(result.model)

        if pricing is None:
            raise UpstreamError(
                f"No pricing configured for provider-returned "
                f"model '{result.model}'."
            )

        cost = CostCalculator.calculate(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            model_pricing=pricing,
        )

        context.cost_usd = cost

        if context.key_config is None:
            raise UpstreamError(
                "Authenticated key configuration is missing."
            )

        month = context.start_time.strftime("%Y-%m")

        usage_repository.record_usage(
            key_hash=context.key_config.key_hash,
            month=month,
            cost=cost,
            tokens=result.total_tokens,
            is_cache_hit=context.cache_status == "hit",
        )

        context.decision_trace.append(
            f"cost: ${cost:.6f}"
        )

        return context

    stages = [
        auth_stage,
        validate_stage,
        rate_limit_stage,
        allowlist_stage,
        budget_stage,
        provider_call_stage,
    ]

    pipeline = getattr(
        request.app.state,
        "pipeline",
        None,
    ) or Pipeline()

    context = await pipeline.run(
        context,
        stages=stages,
    )

    logger.info(
        "Decision trace: %s",
        " → ".join(context.decision_trace),
        extra={
            "path": "/v1/chat/completions",
            "model": context.model_requested,
        },
    )

    # ---------------------------------------------------------
    # Streaming response path
    # ---------------------------------------------------------
    if context.stream:
        loaded_config = request.app.state.loaded_config
        adapter = get_provider_adapter(request)

        # Headers are finalized before StreamingResponse begins.
        headers = build_streaming_headers(context)

        provider_stream = adapter.stream(
            context.request_payload
        )

        streaming_body = format_streaming_body(
            provider_stream=provider_stream,
            context=context,
            usage_repository=usage_repository,
            loaded_config=loaded_config,
            adapter=adapter,
        )

        return StreamingResponse(
            streaming_body,
            status_code=200,
            media_type="text/event-stream",
            headers=headers,
        )

    # ---------------------------------------------------------
    # Existing non-streaming response path
    # ---------------------------------------------------------
    if context.provider_response is None:
        raise UpstreamError(
            "Pipeline completed without a provider response"
        )

    set_context_headers(response, context)

    logger.info(
        "Provider response received",
        extra={
            "path": "/v1/chat/completions",
            "model": context.model_resolved,
        },
    )

    return format_completion_response(
        context.provider_response
    )
