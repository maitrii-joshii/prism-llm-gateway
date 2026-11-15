"""Unit tests for streaming provider execution."""

import httpx
import pytest

from prism.domain.errors import UpstreamError
from prism.services.providers.streaming_execution import (
    StreamingProvider,
    StreamingProviderExecutor,
)


def http_error(status_code: int) -> UpstreamError:
    """Create an UpstreamError caused by an HTTP status error."""

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


def connection_error() -> UpstreamError:
    """Create an UpstreamError caused by a connection failure."""

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


class SequenceStreamingProvider:
    """Fake streaming provider with configurable outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.call_count = 0

    def stream(self, request):
        self.call_count += 1
        return self._generate()

    async def _generate(self):
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        for event in outcome:
            if isinstance(event, Exception):
                raise event

            yield event


def create_provider(adapter, model_name, provider_name):
    return StreamingProvider(
        adapter=adapter,
        model_name=model_name,
        provider_name=provider_name,
    )


@pytest.mark.asyncio
async def test_returns_first_event_and_remaining_stream():
    first_event = {"choices": [{"delta": {"content": "Hello"}}]}
    second_event = {"choices": [{"delta": {"content": " world"}}]}

    adapter = SequenceStreamingProvider(
        [[first_event, second_event]]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(adapter, "test-model", "test-provider")
        ],
        max_retries=1,
        base_delay=0,
    )

    result = await executor.execute({"messages": []})

    events = [
        event async for event in result.provider_stream
    ]

    assert result.first_event == first_event
    assert events == [first_event, second_event]
    assert result.provider_name == "test-provider"
    assert result.model_name == "test-model"
    assert result.retries == 0
    assert result.fallback_used is False
    assert adapter.call_count == 1


@pytest.mark.asyncio
async def test_retries_same_provider_on_http_500():
    first_event = {"choices": [{"delta": {"content": "Success"}}]}

    adapter = SequenceStreamingProvider(
        [
            http_error(500),
            [first_event],
        ]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(adapter, "test-model", "provider-a")
        ],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"messages": []})

    assert result.first_event == first_event
    assert result.retries == 1
    assert result.fallback_used is False
    assert adapter.call_count == 2


@pytest.mark.asyncio
async def test_fails_over_on_connection_error():
    primary = SequenceStreamingProvider(
        [connection_error()]
    )

    backup_event = {"choices": [{"delta": {"content": "Backup"}}]}

    backup = SequenceStreamingProvider(
        [[backup_event]]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(primary, "model-a", "provider-a"),
            create_provider(backup, "model-b", "provider-b"),
        ],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"messages": []})

    assert result.first_event == backup_event
    assert result.provider_name == "provider-b"
    assert result.model_name == "model-b"
    assert result.retries == 0
    assert result.fallback_used is True
    assert primary.call_count == 1
    assert backup.call_count == 1


@pytest.mark.asyncio
async def test_stops_immediately_on_http_400():
    primary = SequenceStreamingProvider(
        [http_error(400)]
    )

    backup = SequenceStreamingProvider(
        [[{"done": True}]]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(primary, "model-a", "provider-a"),
            create_provider(backup, "model-b", "provider-b"),
        ],
        max_retries=2,
        base_delay=0,
    )

    with pytest.raises(UpstreamError):
        await executor.execute({"messages": []})

    assert primary.call_count == 1
    assert backup.call_count == 0


@pytest.mark.asyncio
async def test_raises_when_all_providers_fail():
    primary = SequenceStreamingProvider(
        [http_error(500), http_error(500)]
    )

    backup = SequenceStreamingProvider(
        [connection_error()]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(primary, "model-a", "provider-a"),
            create_provider(backup, "model-b", "provider-b"),
        ],
        max_retries=1,
        base_delay=0,
    )

    with pytest.raises(UpstreamError):
        await executor.execute({"messages": []})

    assert primary.call_count == 2
    assert backup.call_count == 1


@pytest.mark.asyncio
async def test_does_not_retry_failure_after_first_event():
    first_event = {"choices": [{"delta": {"content": "Partial"}}]}

    primary = SequenceStreamingProvider(
        [
            [first_event, UpstreamError("Stream interrupted")]
        ]
    )

    backup = SequenceStreamingProvider(
        [[{"choices": [{"delta": {"content": "Backup"}}]}]]
    )

    executor = StreamingProviderExecutor(
        providers=[
            create_provider(primary, "model-a", "provider-a"),
            create_provider(backup, "model-b", "provider-b"),
        ],
        max_retries=2,
        base_delay=0,
    )

    result = await executor.execute({"messages": []})

    assert result.first_event == first_event

    # The returned iterator includes the prefetched first event.
    received_events = []

    with pytest.raises(UpstreamError):
        async for event in result.provider_stream:
            received_events.append(event)

    assert received_events == [first_event]
    assert primary.call_count == 1
    assert backup.call_count == 0


def test_executor_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        StreamingProviderExecutor(providers=[])


def test_executor_rejects_negative_retries():
    adapter = SequenceStreamingProvider([])

    with pytest.raises(ValueError):
        StreamingProviderExecutor(
            providers=[
                create_provider(adapter, "test-model", "provider-a")
            ],
            max_retries=-1,
        )


def test_executor_rejects_non_positive_timeout():
    adapter = SequenceStreamingProvider([])

    with pytest.raises(ValueError):
        StreamingProviderExecutor(
            providers=[
                create_provider(adapter, "test-model", "provider-a")
            ],
            request_timeout=0,
        )
