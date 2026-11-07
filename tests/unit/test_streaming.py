"""Unit tests for the Prism LLM Gateway streaming proxy.

Covers immediate chunk forwarding, usage recording, provider errors,
client disconnects, cleanup, and idle timeout handling.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from prism.domain.errors import UpstreamError
from prism.domain.models import (
    GatewayConfig,
    ModelPricing,
    RequestContext,
    VirtualKeyConfig,
)
from prism.services.streaming import stream_response


@pytest.fixture
def context():
    return RequestContext(
        request_id="req-123",
        key_config=VirtualKeyConfig(
            key_hash="test-key-hash",
            tenant_id="tenant-1",
            budget_usd=10.0,
            rate_limit_rpm=100,
            model_allowlist=["test-model"],
            cache_enabled=False,
            cache_threshold=0.9,
            status="active",
        ),
        model_requested="test-model",
        model_resolved="test-model",
        start_time=datetime(2026, 11, 2, tzinfo=timezone.utc),
        stream=True,
    )


@pytest.fixture
def config():
    return GatewayConfig(
        model_pricing={
            "test-model": ModelPricing(
                model_name="test-model",
                input_price_per_million=2.0,
                output_price_per_million=4.0,
            )
        }
    )


@pytest.fixture
def usage_repository():
    return MagicMock()


@pytest.fixture
def adapter():
    return MagicMock(last_stream_usage=None)


def make_usage_chunk():
    return {
        "id": "chatcmpl-test",
        "choices": [{"delta": {}, "finish_reason": None}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


@pytest.mark.asyncio
async def test_chunks_are_forwarded_immediately(
    context,
    config,
    usage_repository,
    adapter,
):
    async def provider_stream():
        yield {"choices": [{"delta": {"content": "Hello"}}]}
        yield make_usage_chunk()
        yield {"done": True}

    stream = stream_response(
        provider_stream(),
        context,
        usage_repository,
        config,
        adapter,
    )

    first_chunk = await anext(stream)

    assert '"Hello"' in first_chunk

    # The next provider event has not been consumed yet.
    assert usage_repository.record_usage.call_count == 0

    remaining = [chunk async for chunk in stream]

    assert len(remaining) == 2
    usage_repository.record_usage.assert_called_once()


@pytest.mark.asyncio
async def test_usage_is_recorded_after_normal_completion(
    context,
    config,
    usage_repository,
    adapter,
):
    async def provider_stream():
        yield {"choices": [{"delta": {"content": "Hello"}}]}
        yield make_usage_chunk()
        yield {"done": True}

    chunks = [
        chunk
        async for chunk in stream_response(
            provider_stream(),
            context,
            usage_repository,
            config,
            adapter,
        )
    ]

    assert len(chunks) == 3

    usage_repository.record_usage.assert_called_once_with(
        key_hash="test-key-hash",
        month="2026-11",
        cost=0.00004,
        tokens=15,
        is_cache_hit=False,
    )

    assert context.cost_usd == pytest.approx(0.00004)


@pytest.mark.asyncio
async def test_provider_failure_sends_sse_error_and_records_partial_usage(
    context,
    config,
    usage_repository,
    adapter,
):
    """Provider failure sends an SSE error and persists partial usage."""

    async def provider_stream():
        yield make_usage_chunk()
        raise UpstreamError("Provider connection lost")

    chunks = [
        chunk
        async for chunk in stream_response(
            provider_stream(),
            context,
            usage_repository,
            config,
            adapter,
        )
    ]

    # The client receives an SSE error instead of an exception.
    assert any("event: error" in chunk for chunk in chunks)
    assert any("Provider disconnected" in chunk for chunk in chunks)
    assert any("upstream_error" in chunk for chunk in chunks)

    # Partial usage is still recorded.
    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)

    # The decision trace identifies the upstream failure.
    assert any(
        "upstream_error" in entry
        for entry in context.decision_trace
    )


@pytest.mark.asyncio
async def test_usage_is_recorded_when_client_disconnects(
    context,
    config,
    usage_repository,
    adapter,
):
    async def provider_stream():
        yield make_usage_chunk()
        yield {"choices": [{"delta": {"content": "Hello"}}]}

    stream = stream_response(
        provider_stream(),
        context,
        usage_repository,
        config,
        adapter,
    )

    first_chunk = await anext(stream)

    assert '"usage"' in first_chunk

    await stream.aclose()

    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)


@pytest.mark.asyncio
async def test_provider_stream_is_closed_when_client_disconnects(
    context,
    config,
    usage_repository,
    adapter,
):
    """Closing the downstream stream closes the provider iterator."""

    cleanup_called = False

    async def provider_stream():
        nonlocal cleanup_called

        try:
            yield make_usage_chunk()

            yield {
                "choices": [
                    {"delta": {"content": "Hello"}}
                ]
            }

        finally:
            cleanup_called = True

    stream = stream_response(
        provider_stream(),
        context,
        usage_repository,
        config,
        adapter,
    )

    first_chunk = await anext(stream)

    assert '"usage"' in first_chunk

    await stream.aclose()

    assert cleanup_called is True

    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)


@pytest.mark.asyncio
async def test_cleanup_runs_when_usage_is_unavailable(
    context,
    config,
    usage_repository,
    adapter,
):
    async def provider_stream():
        yield {"choices": [{"delta": {"content": "Hello"}}]}

    stream = stream_response(
        provider_stream(),
        context,
        usage_repository,
        config,
        adapter,
    )

    chunks = [chunk async for chunk in stream]

    assert len(chunks) == 1

    usage_repository.record_usage.assert_not_called()


@pytest.mark.asyncio
async def test_usage_is_recorded_when_stream_idle_timeout_occurs(
    context,
    config,
    usage_repository,
    adapter,
    monkeypatch,
):
    """Partial usage is recorded when the provider becomes idle."""

    monkeypatch.setenv("PRISM_STREAM_IDLE_TIMEOUT", "0.05")

    async def provider_stream():
        # Send usage first.
        yield make_usage_chunk()

        # Simulate a provider that stops sending chunks.
        await asyncio.sleep(1)

    chunks = [
        chunk
        async for chunk in stream_response(
            provider_stream(),
            context,
            usage_repository,
            config,
            adapter,
        )
    ]

    # Verify that an SSE error event is sent.
    assert any("event: error" in chunk for chunk in chunks)

    # Verify that the error identifies an upstream timeout.
    assert any("upstream_error" in chunk for chunk in chunks)

    # Verify that usage is recorded despite the timeout.
    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)

    # Verify that the timeout is recorded in the decision trace.
    assert any(
        "stream idle timeout" in entry
        for entry in context.decision_trace
    )
