"""Unit tests for the Prism LLM Gateway streaming proxy.

Covers:
- Immediate chunk forwarding
- Usage recording
- Provider errors
- Client disconnects
- Provider cleanup
- Idle timeout handling
- StreamingCompletionService orchestration
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
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
from prism.services.chat_streaming import StreamingCompletionService
import prism.services.chat_streaming as chat_streaming


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Streaming lifecycle tests
# ---------------------------------------------------------------------------


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

    assert any("event: error" in chunk for chunk in chunks)
    assert any("Provider disconnected" in chunk for chunk in chunks)
    assert any("upstream_error" in chunk for chunk in chunks)

    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)

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

    assert any("event: error" in chunk for chunk in chunks)
    assert any("upstream_error" in chunk for chunk in chunks)

    usage_repository.record_usage.assert_called_once()

    assert context.cost_usd == pytest.approx(0.00004)

    assert any(
        "stream idle timeout" in entry
        for entry in context.decision_trace
    )


# ---------------------------------------------------------------------------
# StreamingCompletionService test helpers
# ---------------------------------------------------------------------------


def create_streaming_service():
    """Create a StreamingCompletionService with mocked dependencies."""

    usage_repository = MagicMock()
    loaded_config = MagicMock()
    log_repository = MagicMock()
    cache_service = MagicMock()
    request_logging_service = MagicMock()

    service = StreamingCompletionService(
        usage_repository=usage_repository,
        loaded_config=loaded_config,
        log_repository=log_repository,
        cache_service=cache_service,
        request_logging_service=request_logging_service,
    )

    return service


# ---------------------------------------------------------------------------
# StreamingCompletionService tests
# ---------------------------------------------------------------------------


def test_streaming_service_delegates_cached_response(monkeypatch):
    """Cached requests use the cached streaming response formatter."""

    service = create_streaming_service()

    context = SimpleNamespace(
        cache_status="hit",
        request_payload={"model": "test-model"},
    )

    result = SimpleNamespace(
        context=context,
        stream_adapter=None,
        request_started_at=123.0,
    )

    expected_body = object()
    formatter = MagicMock(return_value=expected_body)

    monkeypatch.setattr(
        chat_streaming,
        "format_cached_streaming_body",
        formatter,
    )

    body = service.create_body(
        result=result,
        raw_api_key="test-api-key",
    )

    assert body is expected_body

    formatter.assert_called_once_with(
        context=context,
        raw_api_key="test-api-key",
        request_logging_service=service.request_logging_service,
        log_repository=service.log_repository,
        request_started_at=123.0,
    )


def test_streaming_service_delegates_provider_response(monkeypatch):
    """Provider requests reuse the stream created by the executor."""

    service = create_streaming_service()

    context = SimpleNamespace(
        cache_status="miss",
        request_payload={"model": "test-model"},
    )

    provider_stream = object()
    adapter = MagicMock()

    execution_result = SimpleNamespace(
        provider_stream=provider_stream,
    )

    result = SimpleNamespace(
        context=context,
        stream_adapter=adapter,
        stream_execution_result=execution_result,
        request_started_at=123.0,
    )

    expected_body = object()
    formatter = MagicMock(return_value=expected_body)

    monkeypatch.setattr(
        chat_streaming,
        "format_streaming_body",
        formatter,
    )

    body = service.create_body(
        result=result,
        raw_api_key="test-api-key",
    )

    assert body is expected_body

    formatter.assert_called_once_with(
        provider_stream=provider_stream,
        context=context,
        usage_repository=service.usage_repository,
        loaded_config=service.loaded_config,
        adapter=adapter,
        raw_api_key="test-api-key",
        request_logging_service=service.request_logging_service,
        log_repository=service.log_repository,
        request_started_at=123.0,
        cache_service=service.cache_service,
    )

    # The service must not open another provider stream.
    adapter.stream.assert_not_called()


def test_streaming_service_raises_error_when_adapter_missing():
    """Provider-backed streaming requires a configured adapter."""

    service = create_streaming_service()

    context = SimpleNamespace(
        cache_status="miss",
        request_payload={"model": "test-model"},
    )

    result = SimpleNamespace(
        context=context,
        stream_adapter=None,
        request_started_at=123.0,
    )

    with pytest.raises(
        UpstreamError,
        match="Provider adapter is not configured",
    ):
        service.create_body(
            result=result,
            raw_api_key="test-api-key",
        )


def test_streaming_service_raises_error_when_execution_result_missing():
    """Provider-backed streaming requires an executor result."""

    service = create_streaming_service()

    context = SimpleNamespace(
        cache_status="miss",
        request_payload={"model": "test-model"},
    )

    result = SimpleNamespace(
        context=context,
        stream_adapter=MagicMock(),
        stream_execution_result=None,
        request_started_at=123.0,
    )

    with pytest.raises(
        UpstreamError,
        match="Streaming execution result is not available",
    ):
        service.create_body(
            result=result,
            raw_api_key="test-api-key",
        )


@pytest.mark.parametrize(
    "missing_dependency",
    [
        "usage_repository",
        "loaded_config",
    ],
)
def test_streaming_service_rejects_missing_required_dependencies(
    missing_dependency,
):
    """Application state must contain required streaming dependencies."""

    state = SimpleNamespace(
        usage_repository=MagicMock(),
        loaded_config=MagicMock(),
        log_repository=MagicMock(),
        cache_service=MagicMock(),
        request_logging_service=MagicMock(),
    )

    setattr(state, missing_dependency, None)

    with pytest.raises(
        UpstreamError,
        match="Streaming dependencies are not configured",
    ):
        StreamingCompletionService.from_app_state(state)


def test_streaming_service_loads_optional_dependencies_from_app_state():
    """Optional streaming dependencies are loaded from application state."""

    state = SimpleNamespace(
        usage_repository=MagicMock(),
        loaded_config=MagicMock(),
        log_repository=MagicMock(),
        cache_service=MagicMock(),
        request_logging_service=MagicMock(),
    )

    service = StreamingCompletionService.from_app_state(state)

    assert service.usage_repository is state.usage_repository
    assert service.loaded_config is state.loaded_config
    assert service.log_repository is state.log_repository
    assert service.cache_service is state.cache_service
    assert (
        service.request_logging_service
        is state.request_logging_service
    )
