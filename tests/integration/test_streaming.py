"""Integration tests for the Prism streaming HTTP endpoint.

Covers SSE responses, usage persistence, completion markers,
non-streaming compatibility, upstream stream idle timeouts,
and partial usage persistence after mid-stream provider failures.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from prism.adapters.sqlite_repos import (
    SQLiteLogRepository,
    SQLiteUsageRepository,
    hash_api_key,
    init_database,
)
from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import PrismError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.domain.models import (
    GatewayConfig,
    ModelPricing,
    VirtualKeyConfig,
)
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "streaming-integration-test-key"


class IdleTimeoutFakeProviderAdapter(FakeProviderAdapter):
    """Fake provider that sends usage and then becomes idle."""

    async def stream(self, request):
        self.stream_call_count += 1
        self.last_request = request

        yield {
            "id": "fake-stream-timeout",
            "object": "chat.completion.chunk",
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": None,
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        await asyncio.sleep(1)


class MidStreamFailureFakeProviderAdapter(FakeProviderAdapter):
    """Fake provider that sends partial usage and then crashes."""

    async def stream(self, request):
        self.stream_call_count += 1
        self.last_request = request

        yield {
            "id": "fake-stream-failure",
            "object": "chat.completion.chunk",
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": "Partial response"
                    },
                    "finish_reason": None,
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "total_tokens": 16,
            },
        }

        raise RuntimeError("Simulated provider disconnection")


def create_test_app():
    """Create a FastAPI application with a fake streaming provider."""

    app = FastAPI(title="Prism Streaming Integration Test")

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "streaming_usage.db"

    init_database(str(database_path))

    app.state.usage_repository = SQLiteUsageRepository(
        str(database_path)
    )
    app.state.log_repository = SQLiteLogRepository(
        str(database_path)
    )
    app.state.temp_dir = temp_dir

    key_config = VirtualKeyConfig(
        key_hash=hash_api_key(TEST_API_KEY),
        tenant_id="streaming-test-tenant",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["gpt-4o-mini"],
        cache_enabled=True,
        cache_threshold=0.8,
        status="active",
    )

    key_repository = Mock()
    key_repository.get_by_hash.return_value = key_config
    app.state.key_repository = key_repository

    app.state.loaded_config = GatewayConfig(
        model_pricing={
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=2.0,
                output_price_per_million=4.0,
            ),
            "gpt-4o-mini": ModelPricing(
                model_name="gpt-4o-mini",
                input_price_per_million=2.0,
                output_price_per_million=4.0,
            ),
        }
    )

    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    fake_adapter = FakeProviderAdapter(latency_seconds=0.01)

    app.state.provider_adapter = fake_adapter
    app.state.fake_adapter = fake_adapter

    return app


@pytest.fixture
def app():
    """Provide an application and clean up its temporary database."""

    test_app = create_test_app()

    yield test_app

    test_app.state.temp_dir.cleanup()


@pytest_asyncio.fixture
async def client(app):
    """Provide an asynchronous HTTP client."""

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


def valid_payload(stream: bool = True):
    """Return a valid chat completion request."""

    return {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": "Count to five",
            }
        ],
        "stream": stream,
    }


@pytest.mark.asyncio
async def test_streaming_response_returns_sse_chunks(client, app):
    """Streaming requests return SSE chunks."""

    response_chunks = []

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=valid_payload(stream=True),
        headers={"x-api-key": TEST_API_KEY},
    ) as response:
        assert response.status_code == 200

        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )

        assert response.headers["x-prism-request-id"]
        assert response.headers["x-prism-provider"] == "alpha/gpt-4o-mini"
        assert response.headers["x-prism-cache"] == "miss"
        assert response.headers["x-prism-fallback"] == "false"
        assert response.headers["x-prism-cost-usd"] == "0"

        async for line in response.aiter_lines():
            if line.startswith("data:"):
                response_chunks.append(line)

    assert len(response_chunks) >= 5
    assert app.state.fake_adapter.stream_call_count == 1


@pytest.mark.asyncio
async def test_streaming_records_usage_after_completion(client, app):
    """Provider usage is persisted after the stream completes."""

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=valid_payload(stream=True),
        headers={"x-api-key": TEST_API_KEY},
    ) as response:
        assert response.status_code == 200
        body = await response.aread()

    assert b"data: [DONE]\n\n" in body

    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_requests == 1
    assert usage.total_tokens == 15

    expected_cost = ((10 * 2.0) + (5 * 4.0)) / 1_000_000

    assert usage.total_spend_usd == pytest.approx(expected_cost)


@pytest.mark.asyncio
async def test_streaming_done_marker_is_final_event(client):
    """The stream ends with the OpenAI-compatible DONE marker."""

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=valid_payload(stream=True),
        headers={"x-api-key": TEST_API_KEY},
    ) as response:
        body = await response.aread()

    events = [
        line
        for line in body.decode().splitlines()
        if line.startswith("data:")
    ]

    assert events
    assert events[-1] == "data: [DONE]"


@pytest.mark.asyncio
async def test_non_streaming_request_still_returns_json(client, app):
    """Non-streaming requests retain the existing JSON behavior."""

    response = await client.post(
        "/v1/chat/completions",
        json=valid_payload(stream=False),
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    assert response.headers["content-type"].startswith(
        "application/json"
    )

    body = response.json()

    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["content"] == (
        "Fake provider response"
    )
    assert body["usage"]["total_tokens"] == 15

    assert app.state.fake_adapter.call_count == 1
    assert app.state.fake_adapter.stream_call_count == 0


@pytest.mark.asyncio
async def test_streaming_idle_timeout_returns_error_and_records_usage(
    client,
    app,
    monkeypatch,
):
    """An idle provider stream returns an SSE error and persists usage."""

    monkeypatch.setenv("PRISM_STREAM_IDLE_TIMEOUT", "0.05")

    idle_adapter = IdleTimeoutFakeProviderAdapter()

    app.state.provider_adapter = idle_adapter
    app.state.fake_adapter = idle_adapter

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=valid_payload(stream=True),
        headers={"x-api-key": TEST_API_KEY},
    ) as response:
        assert response.status_code == 200

        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )

        body = await response.aread()

    assert b"event: error" in body
    assert b"upstream_error" in body
    assert b"idle timeout" in body

    assert idle_adapter.stream_call_count == 1

    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_requests == 1
    assert usage.total_tokens == 15

    expected_cost = ((10 * 2.0) + (5 * 4.0)) / 1_000_000

    assert usage.total_spend_usd == pytest.approx(expected_cost)


@pytest.mark.asyncio
async def test_mid_stream_provider_failure_logs_partial_usage(
    client,
    app,
):
    """
    A provider failure after the first chunk sends an SSE error
    and persists the observed partial token counts in request_logs.
    """

    failing_adapter = MidStreamFailureFakeProviderAdapter()

    app.state.provider_adapter = failing_adapter
    app.state.fake_adapter = failing_adapter

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json=valid_payload(stream=True),
        headers={"x-api-key": TEST_API_KEY},
    ) as response:
        assert response.status_code == 200

        request_id = response.headers["x-prism-request-id"]

        body = await response.aread()

    # The partial response was sent before the provider failed.
    assert b"Partial response" in body

    # The stream terminates with an upstream error event.
    assert b"event: error" in body
    assert b"upstream_error" in body
    assert b"Provider disconnected" in body

    assert failing_adapter.stream_call_count == 1

    # Verify partial usage was recorded in the usage repository.
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_requests == 1
    assert usage.total_tokens == 16

    # Verify the request log contains the partial token counts.
    log_entry = app.state.log_repository.get_log(request_id)

    assert log_entry is not None
    assert log_entry.status_code == 502
    assert log_entry.prompt_tokens == 12
    assert log_entry.completion_tokens == 4
    assert log_entry.key_hash == hash_api_key(TEST_API_KEY)

    assert any(
        "error" in trace.lower()
        or "fail" in trace.lower()
        for trace in log_entry.decision_trace
    )
