"""Application service for coordinating chat completion streaming."""

from collections.abc import AsyncIterator
from typing import Any

from prism.domain.errors import UpstreamError
from prism.services.chat_completion import ChatCompletionResult
from prism.services.streaming_response import (
    format_cached_streaming_body,
    format_streaming_body,
)


class StreamingCompletionService:
    """Coordinate cached and provider-backed streaming responses."""

    def __init__(
        self,
        *,
        usage_repository: Any,
        loaded_config: Any,
        log_repository: Any = None,
        cache_service: Any = None,
        request_logging_service: Any = None,
    ) -> None:
        self.usage_repository = usage_repository
        self.loaded_config = loaded_config
        self.log_repository = log_repository
        self.cache_service = cache_service
        self.request_logging_service = request_logging_service

    @classmethod
    def from_app_state(cls, state: Any) -> "StreamingCompletionService":
        """Build the service using dependencies initialized at startup."""

        required = (
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
                "Streaming dependencies are not configured: "
                + ", ".join(missing)
            )

        return cls(
            usage_repository=state.usage_repository,
            loaded_config=state.loaded_config,
            log_repository=getattr(state, "log_repository", None),
            cache_service=getattr(state, "cache_service", None),
            request_logging_service=getattr(
                state,
                "request_logging_service",
                None,
            ),
        )

    def create_body(
        self,
        result: ChatCompletionResult,
        raw_api_key: str | None,
    ) -> AsyncIterator[str]:
        """Create the appropriate streaming body for a processed request."""

        context = result.context

        if context.cache_status == "hit":
            return format_cached_streaming_body(
                context=context,
                raw_api_key=raw_api_key,
                request_logging_service=self.request_logging_service,
                log_repository=self.log_repository,
                request_started_at=result.request_started_at,
            )

        adapter = result.stream_adapter

        if adapter is None:
            raise UpstreamError(
                "Provider adapter is not configured for streaming."
            )

        execution_result = result.stream_execution_result

        if execution_result is None:
            raise UpstreamError(
                "Streaming execution result is not available."
            )

        # Reuse the stream already opened by StreamingProviderExecutor.
        # It includes the prefetched first event and remaining events.
        provider_stream = execution_result.provider_stream

        return format_streaming_body(
            provider_stream=provider_stream,
            context=context,
            usage_repository=self.usage_repository,
            loaded_config=self.loaded_config,
            adapter=adapter,
            raw_api_key=raw_api_key,
            request_logging_service=self.request_logging_service,
            log_repository=self.log_repository,
            request_started_at=result.request_started_at,
            cache_service=self.cache_service,
        )
