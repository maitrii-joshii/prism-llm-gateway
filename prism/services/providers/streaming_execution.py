"""Streaming provider execution with pre-stream retries and failover."""

import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from prism.domain.errors import UpstreamError
from prism.ports.provider import ProviderAdapter
from prism.services.executor import ResilientExecutor


@dataclass
class StreamingProvider:
    """Bind a provider adapter to a model and provider name."""

    adapter: ProviderAdapter
    model_name: str
    provider_name: str

    def stream(
        self,
        request: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Start streaming with the model assigned to this provider."""

        provider_request = request.copy()
        provider_request["model"] = self.model_name

        return self.adapter.stream(provider_request)


@dataclass
class StreamingExecutionResult:
    """Selected provider stream and its execution metadata."""

    provider_stream: AsyncIterator[dict[str, Any]]
    first_event: dict[str, Any]
    retries: int
    fallback_used: bool
    provider_name: str
    model_name: str


class StreamingProviderExecutor:
    """Establish a provider stream with retries and failover.

    Retries and failover are allowed only before the first event
    is received. Once the first event is received, the selected
    provider is retained for the lifetime of the stream.
    """

    def __init__(
        self,
        providers: Sequence[StreamingProvider],
        max_retries: int = 2,
        base_delay: float = 1.0,
        request_timeout: float = 30.0,
    ) -> None:
        if not providers:
            raise ValueError("At least one provider is required")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        if base_delay < 0:
            raise ValueError("base_delay cannot be negative")

        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")

        self.providers = list(providers)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.request_timeout = request_timeout

    async def execute(
        self,
        request: dict[str, Any],
    ) -> StreamingExecutionResult:
        """Establish a stream, retrying or failing over if necessary."""

        total_retries = 0
        last_error: Exception | None = None

        for provider_index, provider in enumerate(self.providers):
            for attempt in range(self.max_retries + 1):
                provider_stream: AsyncIterator[dict[str, Any]] | None = None

                try:
                    provider_stream = provider.stream(request)

                    # Consume only the first event to trigger the
                    # upstream connection and detect early failures.
                    async with asyncio.timeout(self.request_timeout):
                        first_event = await anext(provider_stream)

                    return StreamingExecutionResult(
                        provider_stream=prepend_event(
                            first_event,
                            provider_stream,
                        ),
                        first_event=first_event,
                        retries=total_retries,
                        fallback_used=provider_index > 0,
                        provider_name=provider.provider_name,
                        model_name=provider.model_name,
                    )

                except asyncio.CancelledError:
                    if provider_stream is not None:
                        await close_stream(provider_stream)
                    raise

                except StopAsyncIteration:
                    error = UpstreamError(
                        "Provider stream ended before sending its first event."
                    )
                    last_error = error

                    if provider_stream is not None:
                        await close_stream(provider_stream)

                    if attempt < self.max_retries:
                        total_retries += 1
                        await self._backoff(attempt)
                        continue

                    break

                except Exception as exc:
                    if provider_stream is not None:
                        await close_stream(provider_stream)

                    category = ResilientExecutor._classify_error(exc)
                    last_error = exc

                    if category == "fatal":
                        raise UpstreamError(
                            f"Provider streaming failed with a fatal error: {exc}"
                        ) from exc

                    if category == "retryable":
                        if attempt < self.max_retries:
                            total_retries += 1
                            await self._backoff(attempt)
                            continue

                    # Failover-worthy errors and exhausted retries
                    # move to the next configured provider.
                    break

        raise UpstreamError(
            "All configured providers failed to establish a stream."
        ) from last_error

    async def _backoff(self, attempt: int) -> None:
        """Wait using exponential backoff with random jitter."""

        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.5)

        await asyncio.sleep(delay + jitter)


async def prepend_event(
    first_event: dict[str, Any],
    remaining_stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Yield the prefetched event and close the original stream."""

    try:
        yield first_event

        async for event in remaining_stream:
            yield event

    finally:
        # Closing this wrapper must also close the original provider
        # iterator, including when the downstream client disconnects.
        await close_stream(remaining_stream)


async def close_stream(
    provider_stream: AsyncIterator[dict[str, Any]],
) -> None:
    """Close an upstream iterator when it supports aclose()."""

    close_method = getattr(provider_stream, "aclose", None)

    if close_method is None:
        return

    try:
        await close_method()
    except Exception:
        # Cleanup should not hide the original provider failure.
        pass
