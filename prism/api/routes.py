"""API routes for the Prism LLM Gateway."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from prism.config.logging import get_logger
from prism.domain.cost import CostCalculator
from prism.domain.errors import (
    InvalidRequestError,
    PrismError,
    UpstreamError,
)
from prism.domain.models import LogEntry, ProviderResponse, RequestContext
from prism.domain.security import hash_api_key
from prism.ports.provider import ProviderAdapter
from prism.services.executor import ResilientExecutor
from prism.services.metrics import metrics_registry
from prism.services.pipeline import Pipeline
from prism.services.streaming import stream_response
from prism.services.stages.auth import authenticate_request
from prism.services.stages.allowlist import enforce_model_allowlist
from prism.services.stages.budget import enforce_budget
from prism.services.stages.cache import create_cache_stage
from prism.services.stages.rate_limiter import enforce_rate_limit
from prism.services.stages.resolve import (
    get_gateway_config,
    get_model_pricing,
    resolve_model_candidates,
)
from prism.services.stages.validate import validate_request

router = APIRouter()

_CONSOLE_HTML = (
    Path(__file__).resolve().parent.parent.parent / "console" / "index.html"
)


@router.get("/", include_in_schema=False)
@router.get("/console", include_in_schema=False)
@router.get("/console/", include_in_schema=False)
async def route_ops_console():
    """Serve the ops console HTML directly from the router."""
    if _CONSOLE_HTML.is_file():
        return HTMLResponse(content=_CONSOLE_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>console/index.html not found on disk</h1>",
        status_code=404,
    )


@router.get("/v1/models", tags=["Models"])
async def list_models(request: Request) -> JSONResponse:
    """Return the list of available models and aliases.

    OpenAI-compatible client SDKs (e.g. ``openai`` Python/TS library)
    often probe this endpoint to verify connectivity and discover
    available model names.
    """

    loaded_config = getattr(request.app.state, "loaded_config", None)
    models: list[dict[str, Any]] = []

    if loaded_config:
        # Include all configured aliases (fast, smart, auto).
        for alias_name in loaded_config.gateway_config.aliases:
            models.append({
                "id": alias_name,
                "object": "model",
                "owned_by": "prism",
                "permission": [],
            })

        # Include all underlying model names from the pricing table.
        for model_name in loaded_config.model_pricing:
            models.append({
                "id": model_name,
                "object": "model",
                "owned_by": "provider",
                "permission": [],
            })
    else:
        # Minimal default fallback.
        models = [
            {"id": "fast", "object": "model", "owned_by": "prism"},
            {"id": "smart", "object": "model", "owned_by": "prism"},
            {"id": "auto", "object": "model", "owned_by": "prism"},
        ]

    return JSONResponse(content={"object": "list", "data": models})


@router.get("/metrics", tags=["Observability"])
async def get_prometheus_metrics() -> Response:
    """Export Prometheus-compatible metrics for monitoring."""
    metrics_text = metrics_registry.format_prometheus()
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

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
        provider_request = request.copy()
        provider_request["model"] = self.model_name
        return await self.adapter.complete(provider_request)

    def stream(
        self,
        request: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        provider_request = request.copy()
        provider_request["model"] = self.model_name
        return self.adapter.stream(provider_request)


def save_request_log(
    request: Request,
    context: RequestContext,
    log_repository: Any,
    status_code: int,
    request_started_at: float,
) -> None:
    """Persist request metadata without storing secrets or prompts."""
    if log_repository is None:
        logger.warning(
            "Request log repository is not configured",
            extra={"request_id": context.request_id},
        )
        return

    try:
        key_hash = (
            context.key_config.key_hash
            if context.key_config is not None
            else None
        )

        if key_hash is None:
            raw_key = request.headers.get("x-api-key")
            if raw_key and raw_key.strip():
                key_hash = hash_api_key(raw_key)

        provider_response = context.provider_response

        latency_ms = max(
            0,
            int((time.perf_counter() - request_started_at) * 1000),
        )

        log_entry = LogEntry(
            request_id=context.request_id,
            key_hash=key_hash,
            model_requested=context.model_requested,
            model_resolved=context.model_resolved,
            provider=context.provider_name,
            status_code=status_code,
            prompt_tokens=(
                provider_response.prompt_tokens
                if provider_response is not None
                else context.stream_prompt_tokens
            ),
            completion_tokens=(
                provider_response.completion_tokens
                if provider_response is not None
                else context.stream_completion_tokens
            ),
            cost_usd=context.cost_usd,
            cache_result=context.cache_status,
            fallback_used=context.fallback_used,
            retries=context.retry_count,
            latency_ms=latency_ms,
            decision_trace=list(context.decision_trace),
        )

        log_repository.save_log(log_entry)

        # Record Prometheus metrics
        model_lbl = context.model_resolved or context.model_requested or "unknown"
        provider_lbl = context.provider_name or "none"
        cache_lbl = context.cache_status or "none"
        fallback_lbl = str(context.fallback_used).lower()

        metrics_registry.increment_counter(
            "prism_requests_total",
            1.0,
            {
                "model": model_lbl,
                "provider": provider_lbl,
                "status_code": str(status_code),
                "cache": cache_lbl,
                "fallback": fallback_lbl,
            },
        )
        metrics_registry.observe_duration(
            "prism_request_duration_seconds",
            latency_ms / 1000.0,
        )
        if log_entry.prompt_tokens:
            metrics_registry.increment_counter(
                "prism_tokens_total",
                float(log_entry.prompt_tokens),
                {"type": "prompt"},
            )
        if log_entry.completion_tokens:
            metrics_registry.increment_counter(
                "prism_tokens_total",
                float(log_entry.completion_tokens),
                {"type": "completion"},
            )
        if context.cost_usd > 0:
            metrics_registry.increment_counter(
                "prism_cost_usd_total",
                float(context.cost_usd),
                {"tenant": context.key_config.tenant_id if context.key_config else "unknown"},
            )
        if context.fallback_used:
            metrics_registry.increment_counter(
                "prism_fallback_events_total",
                1.0,
                {"model": model_lbl, "provider": provider_lbl},
            )

        logger.info(
            "Request log saved",
            extra={
                "request_id": context.request_id,
                "status_code": status_code,
                "latency_ms": latency_ms,
            },
        )

    except Exception:
        logger.exception(
            "Failed to save request log",
            extra={"request_id": context.request_id},
        )


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

    if model_name.startswith("gpt-"):
        return "openai"

    if model_name.startswith("llama-"):
        return "groq"

    return getattr(
        adapter,
        "name",
        adapter.__class__.__name__,
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


async def format_cached_streaming_body(
    context: RequestContext,
    request: Request,
    log_repository: Any,
    request_started_at: float,
) -> AsyncIterator[str]:
    """Replay a cached completion as one SSE content chunk."""
    status_code = 200

    try:
        result = context.provider_response

        if result is None:
            raise UpstreamError(
                "Cached streaming response is missing."
            )

        chunk = {
            "id": f"chatcmpl-{uuid4().hex}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": result.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": result.content,
                    },
                    "finish_reason": None,
                }
            ],
        }

        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except (asyncio.CancelledError, GeneratorExit):
        status_code = 499
        context.decision_trace.append(
            "client disconnected during cached streaming"
        )
        raise

    except Exception:
        status_code = 502
        context.decision_trace.append(
            "cached streaming response failed"
        )
        raise

    finally:
        save_request_log(
            request=request,
            context=context,
            log_repository=log_repository,
            status_code=status_code,
            request_started_at=request_started_at,
        )


async def format_streaming_body(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
    usage_repository: Any,
    loaded_config: Any,
    adapter: Any,
    request: Request,
    log_repository: Any,
    request_started_at: float,
    cache_service: Any = None,
) -> AsyncIterator[str]:
    """Forward SSE chunks, cache successful streams, and save request logs."""
    streaming_generator = stream_response(
        provider_stream=provider_stream,
        context=context,
        usage_repository=usage_repository,
        loaded_config=loaded_config,
        adapter=adapter,
    )

    status_code = 200
    client_disconnected = False
    response_parts: list[str] = []
    finish_reason: str | None = None
    stream_completed = False

    try:
        async for formatted_chunk in streaming_generator:
            is_done_event = False

            for line in formatted_chunk.splitlines():
                if not line.startswith("data:"):
                    continue

                data = line.removeprefix("data:").strip()

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if not isinstance(event, dict):
                    continue

                error = event.get("error")
                if (
                    isinstance(error, dict)
                    and error.get("type") == "upstream_error"
                ):
                    status_code = 502

                choices = event.get("choices", [])
                if isinstance(choices, list):
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue

                        delta = choice.get("delta", {})
                        if isinstance(delta, dict):
                            content = delta.get("content")
                            if isinstance(content, str):
                                response_parts.append(content)

                        reason = choice.get("finish_reason")
                        if isinstance(reason, str):
                            finish_reason = reason

                if event.get("done") is True:
                    is_done_event = True
                    stream_completed = status_code == 200

            if is_done_event:
                yield "data: [DONE]\n\n"
                continue

            yield formatted_chunk

        if status_code == 200:
            stream_completed = True

    except (asyncio.CancelledError, GeneratorExit):
        client_disconnected = True
        status_code = 499
        context.decision_trace.append(
            "client disconnected during streaming"
        )
        raise

    except Exception:
        status_code = 502
        context.decision_trace.append(
            "request failed: upstream_error"
        )
        logger.exception(
            "Streaming response failed",
            extra={"request_id": context.request_id},
        )
        raise

    finally:
        try:
            await streaming_generator.aclose()
        except Exception:
            logger.exception(
                "Failed to close streaming generator",
                extra={"request_id": context.request_id},
            )
            if status_code == 200:
                status_code = 502
                stream_completed = False
                context.decision_trace.append(
                    "stream cleanup failed"
                )
        finally:
            if client_disconnected:
                context.decision_trace.append(
                    "stream terminated by client disconnect"
                )

            if (
                stream_completed
                and cache_service is not None
                and context.key_config is not None
                and context.key_config.cache_enabled
                and context.stream_prompt_tokens >= 0
                and context.stream_completion_tokens >= 0
            ):
                try:
                    cached_response = ProviderResponse(
                        content="".join(response_parts),
                        model=context.model_resolved or "",
                        prompt_tokens=context.stream_prompt_tokens,
                        completion_tokens=context.stream_completion_tokens,
                        total_tokens=(
                            context.stream_prompt_tokens
                            + context.stream_completion_tokens
                        ),
                        finish_reason=finish_reason or "stop",
                        raw_response={"source": "stream"},
                    )
                    context.provider_response = cached_response
                    cache_service.store_response(context)
                except Exception:
                    logger.exception(
                        "Failed to store completed stream in semantic cache",
                        extra={"request_id": context.request_id},
                    )

            save_request_log(
                request=request,
                context=context,
                log_repository=log_repository,
                status_code=status_code,
                request_started_at=request_started_at,
            )


def record_usage_for_completion(
    context: RequestContext,
    usage_repository: Any,
) -> None:
    """Record usage for non-streaming requests and cache hits."""
    if context.provider_response is None:
        return

    if context.key_config is None:
        raise UpstreamError(
            "Authenticated key configuration is missing."
        )

    usage_repository.record_usage(
        key_hash=context.key_config.key_hash,
        month=context.start_time.strftime("%Y-%m"),
        cost=context.cost_usd,
        tokens=context.provider_response.total_tokens,
        is_cache_hit=context.cache_status == "hit",
    )

    context.decision_trace.append(
        f"usage recorded: {context.provider_response.total_tokens} tokens"
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
    response: Response,
) -> Any:
    """Process a chat completion request through the pipeline."""
    request_started_at = time.perf_counter()

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

    log_repository = getattr(
        request.app.state,
        "log_repository",
        None,
    )
    cache_service = getattr(
        request.app.state,
        "cache_service",
        None,
    )

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
        # A cache hit already has a complete response.
        if context.cache_status == "hit":
            context.cost_usd = 0.0
            context.decision_trace.append(
                "provider execution skipped: semantic cache hit"
            )
            return context

        loaded_config = getattr(
            request.app.state,
            "loaded_config",
            None,
        )
        if loaded_config is None:
            raise UpstreamError(
                "Gateway configuration is not loaded"
            )

        # Streaming uses the resolved primary provider.
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

        # Non-streaming path: retry and failover execution.
        adapters = get_provider_adapters(request)

        if not adapters:
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

            executor = ResilientExecutor(
                providers=providers,
                max_retries=gateway_config.max_retries,
                base_delay=(
                    getattr(gateway_config, "retry_base_delay_seconds", None)
                    if getattr(gateway_config, "retry_base_delay_seconds", None)
                    is not None
                    else getattr(
                        settings,
                        "retry_base_delay_seconds",
                        1.0,
                    )
                ),
                connect_timeout=getattr(
                    settings,
                    "connect_timeout_seconds",
                    5.0,
                ),
                request_timeout=(
                    gateway_config.provider_timeout_seconds
                ),
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

        pricing_map = get_model_pricing(loaded_config)
        pricing = pricing_map.get(context.model_resolved)
        if pricing is None and "/" in context.model_resolved:
            stripped = context.model_resolved.split("/", 1)[1]
            pricing = pricing_map.get(stripped)
            if pricing is not None:
                context.model_resolved = stripped

        if pricing is None and context.model_candidates:
            pricing = pricing_map.get(context.model_candidates[0])
            if pricing is not None:
                context.model_resolved = context.model_candidates[0]

        if pricing is None:
            raise UpstreamError(
                f"No pricing configured for provider-returned "
                f"model '{context.model_resolved}'."
            )

        context.cost_usd = CostCalculator.calculate(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            model_pricing=pricing,
        )

        if cache_service is not None:
            try:
                cache_service.store_response(context)
            except Exception:
                logger.exception(
                    "Failed to store response in semantic cache",
                    extra={"request_id": context.request_id},
                )

        context.decision_trace.append(
            f"cost: ${context.cost_usd:.6f}"
        )
        return context

    async def meter_stage(
        context: RequestContext,
    ) -> RequestContext:
        # Streaming misses are metered when their stream completes.
        # Cache hits are metered here using the cached token counts.
        if context.stream and context.cache_status != "hit":
            return context

        record_usage_for_completion(
            context,
            usage_repository,
        )
        return context

    stages = [
        auth_stage,
        validate_stage,
        rate_limit_stage,
        model_resolution_stage,
        allowlist_stage,
        budget_stage,
    ]

    if cache_service is not None:
        stages.append(create_cache_stage(cache_service))

    stages.extend([
        provider_call_stage,
        meter_stage,
    ])

    pipeline = getattr(
        request.app.state,
        "pipeline",
        None,
    ) or Pipeline()

    try:
        context = await pipeline.run(
            context,
            stages=stages,
        )

    except PrismError as exc:
        context.decision_trace.append(
            f"request failed: {exc.error_type}"
        )
        save_request_log(
            request=request,
            context=context,
            log_repository=log_repository,
            status_code=exc.status_code,
            request_started_at=request_started_at,
        )
        raise

    except Exception:
        context.decision_trace.append(
            "request failed: internal_error"
        )
        save_request_log(
            request=request,
            context=context,
            log_repository=log_repository,
            status_code=500,
            request_started_at=request_started_at,
        )
        raise

    logger.info(
        "Decision trace: %s",
        " → ".join(context.decision_trace),
        extra={
            "path": "/v1/chat/completions",
            "model": context.model_requested,
        },
    )

    # Streaming response path.
    if context.stream:
        headers = build_streaming_headers(context)

        if context.cache_status == "hit":
            cached_stream = format_cached_streaming_body(
                context=context,
                request=request,
                log_repository=log_repository,
                request_started_at=request_started_at,
            )
            return StreamingResponse(
                cached_stream,
                status_code=200,
                media_type="text/event-stream",
                headers=headers,
            )

        loaded_config = request.app.state.loaded_config
        adapters = get_provider_adapters(request)

        if adapters:
            adapter = adapters[context.model_resolved]
        else:
            adapter = get_provider_adapter(request)

        provider_stream = adapter.stream(
            context.request_payload
        )

        streaming_body = format_streaming_body(
            provider_stream=provider_stream,
            context=context,
            usage_repository=usage_repository,
            loaded_config=loaded_config,
            adapter=adapter,
            request=request,
            log_repository=log_repository,
            request_started_at=request_started_at,
            cache_service=cache_service,
        )

        return StreamingResponse(
            streaming_body,
            status_code=200,
            media_type="text/event-stream",
            headers=headers,
        )

    # Non-streaming response path.
    if context.provider_response is None:
        context.decision_trace.append(
            "request failed: missing provider response"
        )
        save_request_log(
            request=request,
            context=context,
            log_repository=log_repository,
            status_code=502,
            request_started_at=request_started_at,
        )
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

    save_request_log(
        request=request,
        context=context,
        log_repository=log_repository,
        status_code=200,
        request_started_at=request_started_at,
    )

    return format_completion_response(
        context.provider_response
    )
