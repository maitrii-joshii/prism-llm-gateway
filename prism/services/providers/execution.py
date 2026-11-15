"""Application service for non-streaming provider execution."""

from typing import Any

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse, RequestContext
from prism.ports.provider import ProviderAdapter
from prism.services.executor import ExecutionResult, ResilientExecutor
from prism.services.stages.resolve import get_gateway_config


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


class ProviderExecutionService:
    """Coordinate provider selection and resilient execution."""

    async def execute(
        self,
        context: RequestContext,
        loaded_config: Any,
        settings: Any,
        provider_adapters: dict[str, ProviderAdapter] | None,
        default_provider: ProviderAdapter | None,
        provider_names: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a non-streaming request using configured providers.

        Supports both the legacy single-provider configuration and
        the multi-provider configuration with retries and failover.
        """

        adapters = provider_adapters or {}

        if not adapters:
            if default_provider is None:
                raise UpstreamError(
                    "Provider adapter is not configured"
                )

            context.decision_trace.append(
                "legacy single provider selected"
            )

            response = await default_provider.complete(
                context.request_payload
            )

            return ExecutionResult(
                response=response,
                retries=0,
                fallback_used=False,
                provider_name="alpha",
            )

        providers: list[ModelBoundProvider] = []

        for model_name in context.model_candidates:
            adapter = adapters.get(model_name)

            if adapter is None:
                raise UpstreamError(
                    f"No provider configured for model '{model_name}'."
                )

            provider_name = self._get_provider_name(
                model_name,
                adapter,
                provider_names,
            )

            providers.append(
                ModelBoundProvider(
                    adapter=adapter,
                    model_name=model_name,
                    provider_name=provider_name,
                )
            )

        gateway_config = get_gateway_config(loaded_config)

        retry_base_delay = getattr(
            gateway_config,
            "retry_base_delay_seconds",
            None,
        )

        if retry_base_delay is None:
            retry_base_delay = getattr(
                settings,
                "retry_base_delay_seconds",
                1.0,
            )

        executor = ResilientExecutor(
            providers=providers,
            max_retries=gateway_config.max_retries,
            base_delay=retry_base_delay,
            connect_timeout=getattr(
                settings,
                "connect_timeout_seconds",
                5.0,
            ),
            request_timeout=gateway_config.provider_timeout_seconds,
        )

        context.decision_trace.append(
            "resilient provider execution started"
        )

        return await executor.execute(context.request_payload)

    @staticmethod
    def _get_provider_name(
        model_name: str,
        adapter: ProviderAdapter,
        provider_names: dict[str, str] | None,
    ) -> str:
        """Resolve a meaningful provider name for a model."""

        if isinstance(provider_names, dict):
            name = provider_names.get(model_name)

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


__all__ = [
    "ModelBoundProvider",
    "ProviderExecutionService",
]
