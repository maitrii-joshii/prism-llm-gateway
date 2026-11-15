"""Application service that orchestrates chat completion requests."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from prism.domain.cost import CostCalculator
from prism.domain.errors import InvalidRequestError, PrismError, UpstreamError
from prism.domain.models import RequestContext
from prism.ports.provider import ProviderAdapter
from prism.services.observability.request_logging import RequestLoggingService
from prism.services.observability.usage_recording import UsageRecordingService
from prism.services.pipeline import Pipeline
from prism.services.providers.execution import ProviderExecutionService
from prism.services.providers.streaming_execution import (
    StreamingExecutionResult,
    StreamingProvider,
    StreamingProviderExecutor,
)
from prism.services.stages.allowlist import enforce_model_allowlist
from prism.services.stages.auth import authenticate_request
from prism.services.stages.budget import enforce_budget
from prism.services.stages.cache import create_cache_stage
from prism.services.stages.rate_limiter import enforce_rate_limit
from prism.services.stages.resolve import (
    get_gateway_config,
    get_model_pricing,
    resolve_model_candidates,
)
from prism.services.stages.validate import validate_request

logger = logging.getLogger(__name__)


@dataclass
class ChatCompletionResult:
    """Result of processing a chat completion request."""

    context: RequestContext
    stream_adapter: ProviderAdapter | None
    request_started_at: float
    stream_execution_result: StreamingExecutionResult | None = None


class ChatCompletionService:
    """Coordinate the business workflow for a chat completion request.

    HTTP concerns such as reading headers and constructing JSON/SSE
    responses remain in the API layer. This service receives the
    extracted API key and request ID as plain values.
    """

    def __init__(
        self,
        *,
        key_repository: Any,
        clock: Any,
        rate_limiter: Any,
        usage_repository: Any,
        log_repository: Any,
        loaded_config: Any,
        settings: Any = None,
        cache_service: Any = None,
        pipeline: Pipeline | None = None,
        provider_adapter: ProviderAdapter | None = None,
        provider_adapters: dict[str, ProviderAdapter] | None = None,
        provider_names: dict[str, str] | None = None,
        provider_execution_service: ProviderExecutionService | None = None,
        usage_recording_service: UsageRecordingService | None = None,
        request_logging_service: RequestLoggingService | None = None,
    ) -> None:
        self.key_repository = key_repository
        self.clock = clock
        self.rate_limiter = rate_limiter
        self.usage_repository = usage_repository
        self.log_repository = log_repository
        self.loaded_config = loaded_config
        self.settings = settings
        self.cache_service = cache_service
        self.pipeline = pipeline or Pipeline()
        self.provider_adapter = provider_adapter
        self.provider_adapters = provider_adapters or {}
        self.provider_names = provider_names or {}

        self.provider_execution_service = (
            provider_execution_service or ProviderExecutionService()
        )

        self.usage_recording_service = (
            usage_recording_service or UsageRecordingService()
        )

        self.request_logging_service = (
            request_logging_service or RequestLoggingService()
        )

    @classmethod
    def from_app_state(cls, state: Any) -> "ChatCompletionService":
        """Build the service from dependencies initialized by application lifespan."""
        required = (
            "key_repository",
            "clock",
            "rate_limiter",
            "usage_repository",
            "loaded_config",
        )

        missing = [
            name
            for name in required
            if getattr(state, name, None) is None
        ]

        if missing:
            raise UpstreamError(
                "Application dependencies are not configured: "
                + ", ".join(missing)
            )

        return cls(
            key_repository=state.key_repository,
            clock=state.clock,
            rate_limiter=state.rate_limiter,
            usage_repository=state.usage_repository,
            log_repository=getattr(state, "log_repository", None),
            loaded_config=state.loaded_config,
            settings=getattr(state, "settings", None),
            cache_service=getattr(state, "cache_service", None),
            pipeline=getattr(state, "pipeline", None),
            provider_adapter=getattr(state, "provider_adapter", None),
            provider_adapters=getattr(state, "provider_adapters", None),
            provider_names=getattr(state, "provider_names", None),
            provider_execution_service=getattr(
                state,
                "provider_execution_service",
                None,
            ),
            usage_recording_service=getattr(
                state,
                "usage_recording_service",
                None,
            ),
            request_logging_service=getattr(
                state,
                "request_logging_service",
                None,
            ),
        )

    def _save_request_log(
        self,
        context: RequestContext,
        status_code: int,
        request_started_at: float,
        raw_api_key: str | None,
    ) -> None:
        """Delegate request logging and metrics to the observability service."""
        self.request_logging_service.save(
            context=context,
            log_repository=self.log_repository,
            status_code=status_code,
            request_started_at=request_started_at,
            raw_api_key=raw_api_key,
        )

    def _get_provider_name(
        self,
        model_name: str,
        adapter: ProviderAdapter,
    ) -> str:
        """Resolve a meaningful provider name for a model."""
        configured_name = self.provider_names.get(model_name)

        if configured_name:
            return configured_name

        if model_name.startswith("gpt-"):
            return "openai"

        if model_name.startswith("llama-"):
            return "groq"

        return getattr(
            adapter,
            "name",
            adapter.__class__.__name__,
        )

    def _build_streaming_providers(
        self,
        context: RequestContext,
    ) -> list[StreamingProvider]:
        """Build the ordered provider candidates for a streaming request."""
        providers: list[StreamingProvider] = []

        if self.provider_adapters:
            for model_name in context.model_candidates:
                adapter = self.provider_adapters.get(model_name)

                if adapter is None:
                    logger.warning(
                        "No streaming adapter configured for model candidate",
                        extra={"model": model_name},
                    )
                    continue

                providers.append(
                    StreamingProvider(
                        adapter=adapter,
                        model_name=model_name,
                        provider_name=self._get_provider_name(
                            model_name,
                            adapter,
                        ),
                    )
                )

        elif self.provider_adapter is not None:
            if not context.model_candidates:
                raise UpstreamError(
                    "No model candidates available for streaming"
                )

            primary_model = context.model_candidates[0]

            providers.append(
                StreamingProvider(
                    adapter=self.provider_adapter,
                    model_name=primary_model,
                    provider_name="alpha",
                )
            )

        if not providers:
            raise UpstreamError(
                "No provider adapters are configured for streaming"
            )

        return providers

    def _create_streaming_executor(
        self,
        providers: list[StreamingProvider],
    ) -> StreamingProviderExecutor:
        """Create a streaming executor using the gateway retry configuration."""
        gateway_config = get_gateway_config(self.loaded_config)

        retry_base_delay = getattr(
            gateway_config,
            "retry_base_delay_seconds",
            None,
        )

        if retry_base_delay is None:
            retry_base_delay = getattr(
                self.settings,
                "retry_base_delay_seconds",
                1.0,
            )

        return StreamingProviderExecutor(
            providers=providers,
            max_retries=gateway_config.max_retries,
            base_delay=retry_base_delay,
            request_timeout=gateway_config.provider_timeout_seconds,
        )

    async def process(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        raw_api_key: str | None,
    ) -> ChatCompletionResult:
        """Authenticate, validate, orchestrate stages, and execute the request."""

        request_started_at = time.perf_counter()

        initial_model = payload.get("model", "")
        initial_messages = payload.get("messages", [])

        context = RequestContext(
            request_id=request_id,
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
            start_time=self.clock.now(),
        )

        stream_adapter: ProviderAdapter | None = None
        stream_execution_result: StreamingExecutionResult | None = None

        async def auth_stage(ctx: RequestContext) -> RequestContext:
            await authenticate_request(
                raw_api_key,
                ctx,
                self.key_repository,
            )
            return ctx

        async def validate_stage(ctx: RequestContext) -> RequestContext:
            validated_payload = validate_request(ctx.request_payload)

            stream = validated_payload.get("stream", False)

            if not isinstance(stream, bool):
                raise InvalidRequestError(
                    "'stream' must be a boolean."
                )

            ctx.request_payload = validated_payload
            ctx.model_requested = validated_payload["model"]
            ctx.messages = validated_payload["messages"]
            ctx.stream = stream
            ctx.decision_trace.append("request validation ok")

            return ctx

        async def model_resolution_stage(
            ctx: RequestContext,
        ) -> RequestContext:
            if self.loaded_config is None:
                raise UpstreamError(
                    "Gateway configuration is not loaded"
                )

            return resolve_model_candidates(
                ctx,
                self.loaded_config,
            )

        async def rate_limit_stage(
            ctx: RequestContext,
        ) -> RequestContext:
            return await enforce_rate_limit(
                ctx,
                self.rate_limiter,
            )

        async def allowlist_stage(
            ctx: RequestContext,
        ) -> RequestContext:
            return await enforce_model_allowlist(ctx)

        async def budget_stage(
            ctx: RequestContext,
        ) -> RequestContext:
            return await enforce_budget(
                ctx,
                self.usage_repository,
            )

        async def provider_call_stage(
            ctx: RequestContext,
        ) -> RequestContext:
            nonlocal stream_adapter
            nonlocal stream_execution_result

            if ctx.cache_status == "hit":
                ctx.cost_usd = 0.0
                ctx.decision_trace.append(
                    "provider execution skipped: semantic cache hit"
                )
                return ctx

            if self.loaded_config is None:
                raise UpstreamError(
                    "Gateway configuration is not loaded"
                )

            if ctx.stream:
                providers = self._build_streaming_providers(ctx)

                streaming_executor = self._create_streaming_executor(
                    providers
                )

                stream_execution_result = await streaming_executor.execute(
                    ctx.request_payload
                )

                selected_model = stream_execution_result.model_name

                if self.provider_adapters:
                    stream_adapter = self.provider_adapters[selected_model]
                else:
                    stream_adapter = self.provider_adapter

                ctx.provider_name = stream_execution_result.provider_name
                ctx.model_resolved = selected_model
                ctx.retry_count = stream_execution_result.retries
                ctx.fallback_used = stream_execution_result.fallback_used

                ctx.request_payload = ctx.request_payload.copy()
                ctx.request_payload["model"] = selected_model

                ctx.decision_trace.append(
                    f"streaming provider {ctx.provider_name} selected"
                )

                ctx.decision_trace.append(
                    f"streaming retry count: {ctx.retry_count}"
                )

                if ctx.fallback_used:
                    ctx.decision_trace.append(
                        "streaming fallback provider used"
                    )

                logger.info(
                    "Starting provider streaming request",
                    extra={
                        "path": "/v1/chat/completions",
                        "model": selected_model,
                        "provider": ctx.provider_name,
                        "retries": ctx.retry_count,
                        "fallback_used": ctx.fallback_used,
                    },
                )

                return ctx

            execution_result = await self.provider_execution_service.execute(
                context=ctx,
                loaded_config=self.loaded_config,
                settings=self.settings,
                provider_adapters=self.provider_adapters or None,
                default_provider=(
                    None if self.provider_adapters else self.provider_adapter
                ),
                provider_names=self.provider_names,
            )

            result = execution_result.response

            ctx.provider_response = result
            ctx.provider_name = execution_result.provider_name
            ctx.model_resolved = result.model
            ctx.retry_count = execution_result.retries
            ctx.fallback_used = execution_result.fallback_used

            if self.provider_adapters:
                ctx.decision_trace.append(
                    f"provider {ctx.provider_name} succeeded"
                )

                ctx.decision_trace.append(
                    f"retry count: {ctx.retry_count}"
                )

                if ctx.fallback_used:
                    ctx.decision_trace.append(
                        "fallback provider used"
                    )

            ctx.decision_trace.append(
                f"{ctx.model_resolved} response received"
            )

            pricing_map = get_model_pricing(self.loaded_config)
            pricing = pricing_map.get(ctx.model_resolved)

            if pricing is None and "/" in ctx.model_resolved:
                stripped = ctx.model_resolved.split("/", 1)[1]
                pricing = pricing_map.get(stripped)

                if pricing is not None:
                    ctx.model_resolved = stripped

            if pricing is None and ctx.model_candidates:
                pricing = pricing_map.get(ctx.model_candidates[0])

                if pricing is not None:
                    ctx.model_resolved = ctx.model_candidates[0]

            if pricing is None:
                raise UpstreamError(
                    "No pricing configured for provider-returned "
                    f"model '{ctx.model_resolved}'."
                )

            ctx.cost_usd = CostCalculator.calculate(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                model_pricing=pricing,
            )

            if self.cache_service is not None:
                try:
                    self.cache_service.store_response(ctx)
                except Exception:
                    logger.exception(
                        "Failed to store response in semantic cache",
                        extra={"request_id": ctx.request_id},
                    )

            ctx.decision_trace.append(
                f"cost: ${ctx.cost_usd:.6f}"
            )

            return ctx

        async def meter_stage(ctx: RequestContext) -> RequestContext:
            if ctx.stream and ctx.cache_status != "hit":
                return ctx

            self.usage_recording_service.record(
                ctx,
                self.usage_repository,
            )

            return ctx

        stages = [
            auth_stage,
            validate_stage,
            rate_limit_stage,
            model_resolution_stage,
            allowlist_stage,
            budget_stage,
        ]

        if self.cache_service is not None:
            stages.append(
                create_cache_stage(self.cache_service)
            )

        stages.extend([
            provider_call_stage,
            meter_stage,
        ])

        try:
            context = await self.pipeline.run(
                context,
                stages=stages,
            )

        except PrismError as exc:
            context.decision_trace.append(
                f"request failed: {exc.error_type}"
            )

            self._save_request_log(
                context,
                exc.status_code,
                request_started_at,
                raw_api_key,
            )

            raise

        except Exception:
            context.decision_trace.append(
                "request failed: internal_error"
            )

            self._save_request_log(
                context,
                500,
                request_started_at,
                raw_api_key,
            )

            raise

        # Successful non-streaming requests are logged here.
        # Streaming requests are logged after their response stream finishes.
        if not context.stream:
            if context.provider_response is None:
                context.decision_trace.append(
                    "request failed: missing provider response"
                )

                self._save_request_log(
                    context,
                    502,
                    request_started_at,
                    raw_api_key,
                )

                raise UpstreamError(
                    "Pipeline completed without a provider response"
                )

            self._save_request_log(
                context,
                200,
                request_started_at,
                raw_api_key,
            )

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

        logger.info(
            "Decision trace: %s",
            " → ".join(context.decision_trace),
            extra={
                "path": "/v1/chat/completions",
                "model": context.model_requested,
            },
        )

        return ChatCompletionResult(
            context=context,
            stream_adapter=stream_adapter,
            request_started_at=request_started_at,
            stream_execution_result=stream_execution_result,
        )
