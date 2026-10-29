from collections.abc import AsyncIterator
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
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url cannot be empty")

        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client = client

    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        """Send a chat completion request and normalize the response."""

        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self.client is None:
                async with httpx.AsyncClient(
                    timeout=self.timeout
                ) as client:
                    response = await client.post(
                        url,
                        headers=headers,
                        json=request,
                        timeout=self.timeout,
                    )
            else:
                response = await self.client.post(
                    url,
                    headers=headers,
                    json=request,
                    timeout=self.timeout,
                )

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise UpstreamError(
                f"Provider request timed out after {self.timeout} seconds"
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
        """Streaming will be implemented in a later task."""
        raise NotImplementedError(
            "Streaming is not implemented yet"
        )
        yield {}
