"""Unit tests for the OpenAI-compatible provider adapter."""

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


def make_sse_response(events: list[str]) -> httpx.Response:
    """Create a mock SSE response."""

    content = "\n\n".join(events) + "\n\n"

    return httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        text=content,
    )


# ---------------------------------------------------------------------
# Non-streaming completion tests
# ---------------------------------------------------------------------


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
async def test_configured_timeouts_are_passed_to_client() -> None:
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
        connect_timeout=3.0,
        request_timeout=5.0,
        client=client,
    )

    await provider.complete(
        {"model": "test-model", "messages": []}
    )

    timeout = client.post.await_args.kwargs["timeout"]

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 5.0
    assert timeout.write == 5.0
    assert timeout.pool == 3.0


def test_default_timeout_is_30_seconds() -> None:
    provider = OpenAICompatibleProvider(
        "https://mock-provider.test",
        "test-api-key",
    )

    assert provider.timeout == 30.0
    assert provider.connect_timeout == 30.0
    assert provider.request_timeout == 30.0


def test_separate_timeouts_are_configured() -> None:
    provider = OpenAICompatibleProvider(
        "https://mock-provider.test",
        "test-api-key",
        connect_timeout=3.0,
        request_timeout=10.0,
    )

    assert provider.connect_timeout == 3.0
    assert provider.request_timeout == 10.0

    assert provider.http_timeout.connect == 3.0
    assert provider.http_timeout.read == 10.0
    assert provider.http_timeout.write == 10.0
    assert provider.http_timeout.pool == 3.0


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


# ---------------------------------------------------------------------
# Streaming tests
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_yields_sse_events() -> None:
    """Streaming events are parsed and yielded to the caller."""

    events = [
        'data: {"id":"chatcmpl-test","choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"id":"chatcmpl-test","choices":[{"delta":{"content":"lo"}}]}',
        (
            'data: {"id":"chatcmpl-test","choices":[{"delta":{}}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":5,'
            '"total_tokens":15}}'
        ),
        "data: [DONE]",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == (
            "https://mock-provider.test/v1/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer test-api-key"

        body = json.loads(request.content)

        assert body["stream"] is True
        assert body["stream_options"]["include_usage"] is True

        return make_sse_response(events)

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        received_events = [
            event
            async for event in provider.stream(
                {
                    "model": "test-model",
                    "messages": [
                        {"role": "user", "content": "Hello"}
                    ],
                }
            )
        ]

    assert len(received_events) == 4

    assert received_events[0]["choices"][0]["delta"]["content"] == "Hel"
    assert received_events[1]["choices"][0]["delta"]["content"] == "lo"
    assert received_events[2]["usage"]["total_tokens"] == 15
    assert received_events[3] == {"done": True}


@pytest.mark.asyncio
async def test_stream_extracts_final_usage() -> None:
    """The adapter stores usage received in the final data chunk."""

    events = [
        (
            'data: {"choices":[{"delta":{}}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":5,'
            '"total_tokens":15}}'
        ),
        "data: [DONE]",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return make_sse_response(events)

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        received = [
            event
            async for event in provider.stream(
                {"model": "test-model", "messages": []}
            )
        ]

    assert received[-1] == {"done": True}
    assert provider.last_stream_usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


@pytest.mark.asyncio
async def test_stream_handles_done_signal() -> None:
    """The stream stops when the provider sends [DONE]."""

    events = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"Should not appear"}}]}',
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        return make_sse_response(events)

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        received = [
            event
            async for event in provider.stream(
                {"model": "test-model", "messages": []}
            )
        ]

    assert len(received) == 2
    assert received[-1] == {"done": True}


@pytest.mark.asyncio
async def test_stream_invalid_json_raises_upstream_error() -> None:
    """Invalid SSE JSON is converted into an upstream error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return make_sse_response(["data: {invalid-json}"])

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        with pytest.raises(
            UpstreamError,
            match="invalid streaming response",
        ):
            async for _ in provider.stream(
                {"model": "test-model", "messages": []}
            ):
                pass


@pytest.mark.asyncio
async def test_stream_connection_error_raises_upstream_error() -> None:
    """A streaming connection failure becomes UpstreamError."""

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

        with pytest.raises(
            UpstreamError,
            match="streaming connection failed",
        ):
            async for _ in provider.stream(
                {"model": "test-model", "messages": []}
            ):
                pass


@pytest.mark.asyncio
async def test_stream_timeout_raises_upstream_error() -> None:
    """A streaming timeout becomes UpstreamError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "stream timed out",
            request=request,
        )

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            timeout=5.0,
            client=client,
        )

        with pytest.raises(
            UpstreamError,
            match="streaming timed out",
        ):
            async for _ in provider.stream(
                {"model": "test-model", "messages": []}
            ):
                pass


@pytest.mark.asyncio
async def test_stream_http_error_raises_upstream_error() -> None:
    """An unsuccessful provider HTTP response becomes UpstreamError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": "unavailable"},
        )

    async with make_client(handler) as client:
        provider = OpenAICompatibleProvider(
            "https://mock-provider.test",
            "test-api-key",
            client=client,
        )

        with pytest.raises(UpstreamError, match="HTTP 503"):
            async for _ in provider.stream(
                {"model": "test-model", "messages": []}
            ):
                pass


# ---------------------------------------------------------------------
# Provider interface test
# ---------------------------------------------------------------------


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
