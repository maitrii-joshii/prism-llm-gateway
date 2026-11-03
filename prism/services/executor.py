"""Resilient provider execution with retries and failover."""

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.ports.provider import ProviderAdapter


@dataclass
class ExecutionResult:
    """Result and metadata from resilient provider execution."""

    response: ProviderResponse
    retries: int
    fallback_used: bool
    provider_name: str


class ResilientExecutor:
    """Execute provider requests with retries, backoff, and failover."""

    def __init__(
        self,
        providers: Sequence[ProviderAdapter],
        max_retries: int = 2,
        base_delay: float = 1.0,
        connect_timeout: float = 5.0,
        request_timeout: float = 30.0,
    ) -> None:
        if not providers:
            raise ValueError("At least one provider is required")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        if base_delay < 0:
            raise ValueError("base_delay cannot be negative")

        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")

        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")

        self.providers = list(providers)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout

    async def execute(
        self,
        request: dict[str, Any],
    ) -> ExecutionResult:
        """Execute a request against providers in the configured order."""

        total_retries = 0
        last_error: Exception | None = None

        for provider_index, provider in enumerate(self.providers):

            # Prefer an explicitly configured provider name.
            provider_name = getattr(
                provider,
                "name",
                provider.__class__.__name__,
            )

            for attempt in range(self.max_retries + 1):
                try:
                    async with asyncio.timeout(self.request_timeout):
                        response = await provider.complete(request)

                    return ExecutionResult(
                        response=response,
                        retries=total_retries,
                        fallback_used=provider_index > 0,
                        provider_name=provider_name,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    category = self._classify_error(exc)
                    last_error = exc

                    # Fatal errors must stop immediately.
                    if category == "fatal":
                        raise UpstreamError(
                            f"Provider request failed with a fatal error: {exc}"
                        ) from exc

                    # Retry transient errors on the same provider.
                    if category == "retryable":
                        if attempt < self.max_retries:
                            total_retries += 1
                            await self._backoff(attempt)
                            continue

                    # Failover-worthy errors or exhausted retries
                    # move execution to the next provider.
                    break

        raise UpstreamError(
            "All configured providers failed."
        ) from last_error

    async def _backoff(self, attempt: int) -> None:
        """Wait using exponential backoff with random jitter."""

        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.5)

        await asyncio.sleep(delay + jitter)

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Classify errors as retryable, failover, or fatal."""

        if isinstance(exc, TimeoutError):
            return "retryable"

        cause = exc.__cause__

        if isinstance(cause, httpx.TimeoutException):
            return "retryable"

        # A connection failure means this provider is unavailable.
        if isinstance(cause, httpx.ConnectError):
            return "failover"

        if isinstance(cause, httpx.RequestError):
            return "retryable"

        if isinstance(cause, httpx.HTTPStatusError):
            status_code = cause.response.status_code

            if status_code == 429:
                return "failover"

            if status_code >= 500:
                return "retryable"

            if 400 <= status_code < 500:
                return "fatal"

        # Generic upstream errors are retryable when their exact
        # underlying cause is unknown.
        if isinstance(exc, UpstreamError):
            return "retryable"

        return "fatal"
