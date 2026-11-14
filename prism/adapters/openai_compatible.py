"""Adapter for providers exposing the OpenAI chat completions API."""

from collections.abc import AsyncIterator

import json
from typing import Any

import httpx

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.ports.provider import ProviderAdapter


class OpenAICompatibleProvider(ProviderAdapter):
    """Adapter for providers exposing the OpenAI chat completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float | None = 30.0,
        client: httpx.AsyncClient | None = None,
        *,
        connect_timeout: float | None = None,
        request_timeout: float | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url cannot be empty")

        # Preserve the old timeout argument for backward compatibility.
        effective_connect_timeout = (
            connect_timeout if connect_timeout is not None else timeout
        )
        effective_request_timeout = (
            request_timeout if request_timeout is not None else timeout
        )

        if effective_connect_timeout is None or effective_connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")

        if effective_request_timeout is None or effective_request_timeout <= 0:
            raise ValueError("request_timeout must be positive")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

        self.connect_timeout = effective_connect_timeout
        self.request_timeout = effective_request_timeout

        # Keep the legacy attribute available.
        self.timeout = self.request_timeout

        self.http_timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.request_timeout,
            write=self.request_timeout,
            pool=self.connect_timeout,
        )

        self.client = client
        self._managed_client: httpx.AsyncClient | None = None
        self.last_stream_usage: dict[str, int] | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or initialize the reusable HTTP client with connection pooling."""
        if self.client is not None:
            return self.client
        if self._managed_client is None or self._managed_client.is_closed:
            self._managed_client = httpx.AsyncClient(
                timeout=self.http_timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=30.0,
                ),
            )
        return self._managed_client

    async def aclose(self) -> None:
        """Gracefully close the managed HTTP client connection pool."""
        if self._managed_client is not None and not self._managed_client.is_closed:
            await self._managed_client.aclose()
            self._managed_client = None

    def _completion_url(self) -> str:
        """Build the chat completion URL without duplicating /v1."""

        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"

        return f"{self.base_url}/v1/chat/completions"

    def _build_headers(self) -> dict[str, str]:
        """Build common headers for provider requests."""

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        """Send a chat completion request and normalize the response."""

        url = self._completion_url()
        headers = self._build_headers()

        try:
            client = self._get_client()
            response = await client.post(
                url,
                headers=headers,
                json=request,
                timeout=self.http_timeout,
            )

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise UpstreamError(
                f"Provider request timed out after "
                f"{self.request_timeout} seconds"
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"Provider returned HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            raise UpstreamError(
                f"Could not connect to provider: {exc}"
            ) from exc

        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage") or {}

            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            return ProviderResponse(
                content=message["content"],
                model=data["model"],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=usage.get(
                    "total_tokens",
                    prompt_tokens + completion_tokens,
                ),
                finish_reason=choice.get("finish_reason"),
                raw_response=data,
            )

        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(
                "Provider returned an invalid chat completion response"
            ) from exc

    async def stream(
        self,
        request: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream parsed SSE events from the provider without buffering."""

        url = self._completion_url()
        headers = self._build_headers()

        stream_request = {
            **request,
            "stream": True,
            "stream_options": {
                **request.get("stream_options", {}),
                "include_usage": True,
            },
        }

        self.last_stream_usage = None

        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=stream_request,
                timeout=self.http_timeout,
            ) as response:
                async for event in self._read_sse_events(response):
                    yield event

        except httpx.TimeoutException as exc:
            raise UpstreamError(
                f"Provider streaming timed out after "
                f"{self.request_timeout} seconds"
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise UpstreamError(
                f"Provider returned HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            raise UpstreamError(
                f"Provider streaming connection failed: {exc}"
            ) from exc

    async def _read_sse_events(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[dict[str, Any]]:
        """Read and parse SSE events as they arrive."""

        response.raise_for_status()

        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue

            if not line.startswith("data:"):
                continue

            data = line[len("data:"):].strip()

            if data == "[DONE]":
                yield {"done": True}
                return

            try:
                event = json.loads(data)
            except json.JSONDecodeError as exc:
                raise UpstreamError(
                    "Provider returned an invalid streaming response"
                ) from exc

            usage = event.get("usage")

            if isinstance(usage, dict):
                self.last_stream_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get(
                        "completion_tokens", 0
                    ),
                    "total_tokens": usage.get("total_tokens", 0),
                }

            yield event
