import json
from unittest.mock import AsyncMock

import httpx
import pytest

from prism.adapters.openai_compatible import OpenAICompatibleProvider
from prism.domain.errors import UpstreamError
from prism.ports.provider import ProviderAdapter


def successful_response() -> dict:
    return {
        "id": "chatcmpl-test",
        "model": "test-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from the mock provider!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 7,
            "total_tokens": 17,
        },
    }


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=30.0,
    )


@pytest.mark.asyncio
async def test_complete_parses_provider_response() -> None:
    expected_body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == (
            "https://mock-provider.test/v1/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer test-api-key"
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content) == expected_body

        return httpx.Response(200, json=successful_response())

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test/",
            "test-api-key",
            client=client,
        )
        result = await provider.complete(expected_body)

    assert result.content == "Hello from the mock provider!"
    assert result.model == "test-model"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 7
    assert result.total_tokens == 17
    assert result.finish_reason == "stop"
    assert result.raw_response["id"] == "chatcmpl-test"


@pytest.mark.asyncio
async def test_non_200_response_raises_upstream_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        with pytest.raises(UpstreamError, match="HTTP 503"):
            await provider.complete(
                {"model": "test-model", "messages": []}
            )


@pytest.mark.asyncio
async def test_connection_error_raises_upstream_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connection refused",
            request=request,
        )

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        with pytest.raises(UpstreamError, match="Could not connect"):
            await provider.complete(
                {"model": "test-model", "messages": []}
            )


@pytest.mark.asyncio
async def test_timeout_raises_upstream_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "request timed out",
            request=request,
        )

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            timeout=5.0,
            client=client,
        )

        with pytest.raises(UpstreamError, match="timed out"):
            await provider.complete(
                {"model": "test-model", "messages": []}
            )


@pytest.mark.asyncio
async def test_configured_timeout_is_passed_to_client() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)

    request = httpx.Request(
        "POST",
        "https://mock-provider.test/v1/chat/completions",
    )

    client.post.return_value = httpx.Response(
        200,
        json=successful_response(),
        request=request,
    )

    provider = OpenAICompatibleProvider(
        "https://mock-provider.test",
        "test-api-key",
        timeout=5.0,
        client=client,
    )

    await provider.complete(
        {"model": "test-model", "messages": []}
    )

    assert client.post.await_args.kwargs["timeout"] == 5.0


def test_default_timeout_is_30_seconds() -> None:
    provider = OpenAICompatibleProvider(
        "https://mock-provider.test",
        "test-api-key",
    )

    assert provider.timeout == 30.0


@pytest.mark.asyncio
async def test_total_tokens_falls_back_to_token_sum() -> None:
    payload = successful_response()
    del payload["usage"]["total_tokens"]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        result = await provider.complete(
            {"model": "test-model", "messages": []}
        )

    assert result.prompt_tokens == 10
    assert result.completion_tokens == 7
    assert result.total_tokens == 17


@pytest.mark.asyncio
async def test_invalid_response_raises_upstream_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        with pytest.raises(UpstreamError, match="invalid"):
            await provider.complete(
                {"model": "test-model", "messages": []}
            )


def test_provider_implements_provider_adapter() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=successful_response())

    client = make_client(handler)
    provider = OpenAICompatibleProvider(
        "https://mock-provider.test",
        "test-api-key",
        client=client,
    )

    assert isinstance(provider, ProviderAdapter)
