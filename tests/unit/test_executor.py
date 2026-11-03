"""Unit tests for the resilient provider executor."""

import httpx
import pytest

from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse
from prism.services.executor import ResilientExecutor
from tests.helpers.fake_adapter import FakeProviderAdapter


def successful_response():
    return ProviderResponse(
        content="Success",
        model="test-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
        raw_response={},
    )


class SequenceProvider:
    """Fake provider that returns or raises configured outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.call_count = 0

    async def complete(self, request):
        self.call_count += 1
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome

    async def stream(self, request):
        raise NotImplementedError


def http_error(status_code):
    """Create an UpstreamError preserving the original HTTP error."""

    request = httpx.Request(
        "POST",
        "https://provider.example.com/v1/chat/completions",
    )

    response = httpx.Response(status_code, request=request)

    original_error = httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )

    error = UpstreamError(f"Provider returned HTTP {status_code}")
    error.__cause__ = original_error

    return error


def connection_error():
    """Create an UpstreamError caused by an HTTPX connection error."""

    request = httpx.Request(
        "POST",
        "https://provider.example.com/v1/chat/completions",
    )

    original_error = httpx.ConnectError(
        "Connection refused",
        request=request,
    )

    error = UpstreamError("Connection failed")
    error.__cause__ = original_error

    return error


@pytest.mark.asyncio
async def test_retries_on_http_500():
    provider = SequenceProvider(
        [http_error(500), successful_response()]
    )

    executor = ResilientExecutor(
        providers=[provider],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"model": "test-model"})

    assert result.response.content == "Success"
    assert result.retries == 1
    assert result.fallback_used is False
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_fails_over_on_connection_error():
    primary = SequenceProvider([connection_error()])
    backup = SequenceProvider([successful_response()])

    executor = ResilientExecutor(
        providers=[primary, backup],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"model": "test-model"})

    assert result.response.content == "Success"
    assert result.retries == 0
    assert result.fallback_used is True
    assert primary.call_count == 1
    assert backup.call_count == 1


@pytest.mark.asyncio
async def test_stops_immediately_on_http_400():
    primary = SequenceProvider([http_error(400)])
    backup = SequenceProvider([successful_response()])

    executor = ResilientExecutor(
        providers=[primary, backup],
        max_retries=2,
        base_delay=0,
    )

    with pytest.raises(UpstreamError):
        await executor.execute({"model": "test-model"})

    assert primary.call_count == 1
    assert backup.call_count == 0


@pytest.mark.asyncio
async def test_fails_over_on_http_429():
    primary = SequenceProvider([http_error(429)])
    backup = SequenceProvider([successful_response()])

    executor = ResilientExecutor(
        providers=[primary, backup],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"model": "test-model"})

    assert result.response.content == "Success"
    assert result.fallback_used is True
    assert primary.call_count == 1
    assert backup.call_count == 1


@pytest.mark.asyncio
async def test_raises_upstream_error_when_all_providers_fail():
    primary = SequenceProvider(
        [http_error(500), http_error(500)]
    )

    backup = SequenceProvider(
        [
            UpstreamError("Backup unavailable"),
            UpstreamError("Backup unavailable"),
        ]
    )

    executor = ResilientExecutor(
        providers=[primary, backup],
        max_retries=1,
        base_delay=0,
    )

    with pytest.raises(UpstreamError):
        await executor.execute({"model": "test-model"})

    assert primary.call_count == 2
    assert backup.call_count == 2


@pytest.mark.asyncio
async def test_retry_count_includes_retries_across_providers():
    primary = SequenceProvider(
        [http_error(500), http_error(500)]
    )

    backup = SequenceProvider(
        [http_error(500), successful_response()]
    )

    executor = ResilientExecutor(
        providers=[primary, backup],
        max_retries=1,
        base_delay=0,
    )

    result = await executor.execute({"model": "test-model"})

    assert result.response.content == "Success"
    assert result.retries == 2
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_retries_on_timeout():
    provider = SequenceProvider(
        [
            TimeoutError("Request timed out"),
            successful_response(),
        ]
    )

    executor = ResilientExecutor(
        providers=[provider],
        max_retries=1,
        base_delay=0,
    )

    result = await executor.execute({"model": "test-model"})

    assert result.response.content == "Success"
    assert result.retries == 1
    assert provider.call_count == 2


def test_executor_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        ResilientExecutor(providers=[])


def test_executor_rejects_negative_retries():
    with pytest.raises(ValueError):
        ResilientExecutor(
            providers=[FakeProviderAdapter()],
            max_retries=-1,
        )


@pytest.mark.asyncio
async def test_executor_respects_request_timeout():
    provider = FakeProviderAdapter(latency_seconds=0.2)

    executor = ResilientExecutor(
        providers=[provider],
        max_retries=0,
        request_timeout=0.05,
    )

    with pytest.raises(UpstreamError):
        await executor.execute({"model": "test-model"})

    assert provider.call_count == 1
