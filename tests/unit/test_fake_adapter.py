import asyncio

import pytest

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.ports.provider import ProviderAdapter
from tests.helpers.fake_adapter import FakeProviderAdapter


def test_fake_adapter_implements_provider_interface() -> None:
    adapter = FakeProviderAdapter()

    assert isinstance(adapter, ProviderAdapter)


@pytest.mark.asyncio
async def test_fake_adapter_returns_default_response() -> None:
    adapter = FakeProviderAdapter()

    result = await adapter.complete(
        {"model": "fake-model", "messages": []}
    )

    assert isinstance(result, ProviderResponse)
    assert result.content == "Fake provider response"
    assert result.model == "fake-model"
    assert result.total_tokens == 15


@pytest.mark.asyncio
async def test_fake_adapter_returns_custom_response() -> None:
    response = ProviderResponse(
        content="Custom response",
        model="custom-model",
        prompt_tokens=3,
        completion_tokens=4,
        total_tokens=7,
        finish_reason="stop",
        raw_response={"custom": True},
    )
    adapter = FakeProviderAdapter(response=response)

    result = await adapter.complete({"model": "custom-model"})

    assert result == response


@pytest.mark.asyncio
async def test_fake_adapter_can_raise_upstream_error() -> None:
    adapter = FakeProviderAdapter(
        error=UpstreamError("Simulated provider failure")
    )

    with pytest.raises(UpstreamError, match="Simulated provider failure"):
        await adapter.complete({"model": "fake-model"})


@pytest.mark.asyncio
async def test_fake_adapter_simulates_latency() -> None:
    adapter = FakeProviderAdapter(latency_seconds=0.05)

    start = asyncio.get_running_loop().time()
    await adapter.complete({"model": "fake-model"})
    elapsed = asyncio.get_running_loop().time() - start

    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_fake_adapter_tracks_calls_and_request() -> None:
    adapter = FakeProviderAdapter()
    request = {"model": "fake-model", "messages": []}

    await adapter.complete(request)
    await adapter.complete(request)

    assert adapter.call_count == 2
    assert adapter.last_request == request


def test_fake_adapter_rejects_negative_latency() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        FakeProviderAdapter(latency_seconds=-1)


def test_fake_adapter_rejects_response_and_error_together() -> None:
    response = ProviderResponse(
        content="Hello",
        model="fake-model",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        raw_response={},
    )

    with pytest.raises(ValueError, match="either response or error"):
        FakeProviderAdapter(
            response=response,
            error=UpstreamError("Simulated failure"),
        )