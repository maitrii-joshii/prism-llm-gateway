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
from prism.domain.errors import (
    InvalidRequestError,
    ModelNotFoundError,
    UpstreamError,
)
from prism.domain.models import ProviderResponse, RequestContext
from prism.ports.provider import ProviderAdapter
from prism.services.pipeline import Pipeline
from prism.services.executor import ResilientExecutor
from prism.services.streaming import stream_response
from prism.services.stages.auth import authenticate_request
from prism.services.stages.allowlist import enforce_model_allowlist
from prism.services.stages.budget import enforce_budget
from prism.services.stages.rate_limiter import enforce_rate_limit
from prism.services.stages.validate import validate_request

router = APIRouter()
logger = get_logger(__name__)


class ModelBoundProvider:
    """Bind a specific model and provider name to an adapter."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        model_name: str,
        provider_name: str,
    ) -> None:
        self.adapter = adapter
        self.model_name = model_name
        self.name = provider_name

    async def complete(
        self,
        request: dict[str, Any],
    ) -> ProviderResponse:
        """Forward a completion request using the bound model."""

        provider_request = request.copy()
        provider_request["model"] = self.model_name

        return await self.adapter.complete(provider_request)

    def stream(
        self,
        request: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Forward a streaming request using the bound model."""

        provider_request = request.copy()
        provider_request["model"] = self.model_name

        return self.adapter.stream(provider_request)


def get_provider_adapter(request: Request) -> ProviderAdapter:
    """Retrieve the legacy single-provider adapter."""

    adapter = getattr(request.app.state, "provider_adapter", None)

    if adapter is None:
        raise UpstreamError("Provider adapter is not configured")

    return adapter


def get_provider_adapters(
    request: Request,
) -> dict[str, ProviderAdapter]:
    """Retrieve adapters indexed by supported model name."""

    adapters = getattr(
        request.app.state,
        "provider_adapters",
        None,
    )

    if not isinstance(adapters, dict):
        return {}

    return adapters


def get_provider_name(
    request: Request,
    model_name: str,
    adapter: ProviderAdapter,
) -> str:
    """Resolve a meaningful provider name for a model."""

    configured_names = getattr(
        request.app.state,
        "provider_names",
        {},
    )

    if isinstance(configured_names, dict):
        name = configured_names.get(model_name)
        if name:
            return name

    # Current Prism model-to-provider mapping.
    if model_name.startswith("gpt-"):
        return "openai"

    if model_name.startswith("llama-"):
        return "groq"

    return getattr(
        adapter,
        "name",
        adapter.__class__.__name__,
    )


def get_gateway_config(loaded_config: Any) -> Any:
    """Support both LoadedConfig and GatewayConfig objects."""

    return getattr(
        loaded_config,
        "gateway_config",
        loaded_config,
    )


def get_model_pricing(loaded_config: Any) -> dict[str, Any]:
    """Retrieve model pricing from the loaded configuration."""

    gateway_config = get_gateway_config(loaded_config)

    return getattr(
        loaded_config,
        "model_pricing",
        getattr(gateway_config, "model_pricing", {}),
    )


def resolve_model_candidates(
    context: RequestContext,
    loaded_config: Any,
) -> RequestContext:
    """Resolve aliases into primary and fallback model candidates."""

    gateway_config = get_gateway_config(loaded_config)

    aliases = gateway_config.aliases
    pricing = get_model_pricing(loaded_config)

    requested_model = context.model_requested

    alias_config = aliases.get(requested_model)

    if alias_config is not None:
        candidates = [
            alias_config.primary_model,
            *alias_config.fallback_chain,
        ]

        context.decision_trace.append(
            f"alias '{requested_model}' resolved"
        )

    else:
        if requested_model not in pricing:
            raise ModelNotFoundError(
                f"Model '{requested_model}' is not configured."
            )

        candidates = [requested_model]

    # Remove duplicate models while preserving order.
    context.model_candidates = list(dict.fromkeys(candidates))

    if not context.model_candidates:
        raise ModelNotFoundError(
            f"No models configured for '{requested_model}'."
        )

    context.model_resolved = context.model_candidates[0]

    context.decision_trace.append(
        "model candidates: "
        + ", ".join(context.model_candidates)
    )

    return context


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
            try:
                data = formatted_chunk.removeprefix("data: ").strip()
                event = json.loads(data)

                if event.get("done") is True:
                    yield "data: [DONE]\n\n"
                    continue

            except (json.JSONDecodeError, AttributeError):
                pass

            yield formatted_chunk

    finally:
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

    async def model_resolution_stage(
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

        return resolve_model_candidates(
            context,
            loaded_config,
        )

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

        # -----------------------------------------------------
        # Streaming path: use the resolved primary provider.
        # Automatic streaming failover is not implemented here.
        # -----------------------------------------------------
        if context.stream:
            primary_model = context.model_candidates[0]
            adapters = get_provider_adapters(request)

            if adapters:
                adapter = adapters.get(primary_model)

                if adapter is None:
                    raise UpstreamError(
                        f"No provider configured for model "
                        f"'{primary_model}'."
                    )

                context.provider_name = get_provider_name(
                    request,
                    primary_model,
                    adapter,
                )

            else:
                adapter = get_provider_adapter(request)
                context.provider_name = "alpha"

            context.model_resolved = primary_model

            context.request_payload = context.request_payload.copy()
            context.request_payload["model"] = primary_model

            context.decision_trace.append(
                f"streaming provider {context.provider_name} selected"
            )

            logger.info(
                "Starting provider streaming request",
                extra={
                    "path": "/v1/chat/completions",
                    "model": primary_model,
                    "provider": context.provider_name,
                },
            )

            return context

        # -----------------------------------------------------
        # Non-streaming path: retry and failover execution.
        # -----------------------------------------------------
        adapters = get_provider_adapters(request)

        if not adapters:
            # Backward compatibility for existing single-provider
            # tests and integrations.
            adapter = get_provider_adapter(request)

            context.provider_name = "alpha"
            context.decision_trace.append(
                "legacy single provider selected"
            )

            result = await adapter.complete(
                context.request_payload
            )

            context.provider_response = result
            context.model_resolved = result.model

        else:
            providers: list[ModelBoundProvider] = []

            for model_name in context.model_candidates:
                adapter = adapters.get(model_name)

                if adapter is None:
                    raise UpstreamError(
                        f"No provider configured for model "
                        f"'{model_name}'."
                    )

                provider_name = get_provider_name(
                    request,
                    model_name,
                    adapter,
                )

                providers.append(
                    ModelBoundProvider(
                        adapter=adapter,
                        model_name=model_name,
                        provider_name=provider_name,
                    )
                )

            settings = getattr(
                request.app.state,
                "settings",
                None,
            )

            gateway_config = get_gateway_config(loaded_config)

            max_retries = gateway_config.max_retries
            request_timeout = (
                gateway_config.provider_timeout_seconds
            )

            connect_timeout = getattr(
                settings,
                "connect_timeout_seconds",
                5.0,
            )

            base_delay = getattr(
                settings,
                "retry_base_delay_seconds",
                1.0,
            )

            executor = ResilientExecutor(
                providers=providers,
                max_retries=max_retries,
                base_delay=base_delay,
                connect_timeout=connect_timeout,
                request_timeout=request_timeout,
            )

            context.decision_trace.append(
                "resilient provider execution started"
            )

            execution_result = await executor.execute(
                context.request_payload
            )

            result = execution_result.response

            context.provider_response = result
            context.provider_name = execution_result.provider_name
            context.model_resolved = result.model
            context.retry_count = execution_result.retries
            context.fallback_used = execution_result.fallback_used

            context.decision_trace.append(
                f"provider {context.provider_name} succeeded"
            )

            context.decision_trace.append(
                f"retry count: {context.retry_count}"
            )

            if context.fallback_used:
                context.decision_trace.append(
                    "fallback provider used"
                )

        context.decision_trace.append(
            f"{context.model_resolved} response received"
        )

        pricing = get_model_pricing(loaded_config).get(
            context.model_resolved
        )

        if pricing is None:
            raise UpstreamError(
                f"No pricing configured for provider-returned "
                f"model '{context.model_resolved}'."
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
        model_resolution_stage,
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
        adapters = get_provider_adapters(request)

        if adapters:
            adapter = adapters[context.model_resolved]
        else:
            adapter = get_provider_adapter(request)

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
    # Non-streaming response path
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
            "provider": context.provider_name,
            "retries": context.retry_count,
            "fallback_used": context.fallback_used,
        },
    )

    return format_completion_response(
        context.provider_response
    )
