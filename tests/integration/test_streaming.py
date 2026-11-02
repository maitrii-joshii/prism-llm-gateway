"""Integration tests for the Prism streaming HTTP endpoint."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from prism.adapters.sqlite_repos import (
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


def create_test_app():
    """Create a FastAPI application with a fake streaming provider."""

    app = FastAPI(title="Prism Streaming Integration Test")

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    # Use a temporary database for usage persistence.
    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "streaming_usage.db"

    init_database(str(database_path))

    app.state.usage_repository = SQLiteUsageRepository(
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

    # Configure pricing for both the fake provider model and the
    # model name resolved by the streaming route.
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

        # Verify all Prism streaming headers.
        assert response.headers["x-prism-request-id"]
        assert response.headers["x-prism-provider"] == "alpha/gpt-4o-mini"
        assert response.headers["x-prism-cache"] == "miss"
        assert response.headers["x-prism-fallback"] == "false"
        assert response.headers["x-prism-cost-usd"] == "0"

        async for line in response.aiter_lines():
            if line.startswith("data:"):
                response_chunks.append(line)

    # The fake adapter emits role, content, usage and DONE events.
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

        # Consume the entire response to allow the stream to finish.
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
