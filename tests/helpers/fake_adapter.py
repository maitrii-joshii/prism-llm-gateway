import asyncio
from collections.abc import AsyncIterator
from typing import Any

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.ports.provider import ProviderAdapter


class FakeProviderAdapter(ProviderAdapter):
    """A configurable provider adapter for tests; makes no network calls."""

    def __init__(
        self,
        response: ProviderResponse | None = None,
        error: UpstreamError | None = None,
        latency_seconds: float = 0.0,
    ) -> None:
        if response is not None and error is not None:
            raise ValueError("Provide either response or error, not both")

        if latency_seconds < 0:
            raise ValueError("latency_seconds cannot be negative")

        self.response = response or ProviderResponse(
            content="Fake provider response",
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
            raw_response={"fake": True},
        )
        self.error = error
        self.latency_seconds = latency_seconds

        self.call_count = 0
        self.last_request: dict[str, Any] | None = None

    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        """Return a canned response or raise a configured error."""

        self.call_count += 1
        self.last_request = request

        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        if self.error is not None:
            raise self.error

        return self.response

    async def stream(
        self,
        request: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming is intentionally not implemented in this fake."""

        raise NotImplementedError(
            "Streaming is not implemented in FakeProviderAdapter"
        )
        yield {}
