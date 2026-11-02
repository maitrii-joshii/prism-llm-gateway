"""Integration tests for the Prism completion pass-through flow."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


TEST_API_KEY = "integration-test-api-key"


@pytest.fixture
def client():
    """Create a test application with a fake provider."""

    app = FastAPI(title="Prism Integration Test")

    # Initialize shared application dependencies.
    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    # Initialize a temporary SQLite database for usage tracking.
    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "test_usage.db"

    init_database(str(database_path))
    app.state.usage_repository = SQLiteUsageRepository(str(database_path))
    app.state.temp_dir = temp_dir

    key_config = VirtualKeyConfig(
        key_hash=hash_api_key(TEST_API_KEY),
        tenant_id="test-tenant",
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

    # Configure pricing for the model returned by the fake provider.
    app.state.loaded_config = GatewayConfig(
        model_pricing={
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            )
        }
    )

    app.middleware("http")(request_id_middleware)

    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    fake_adapter = FakeProviderAdapter()
    app.state.provider_adapter = fake_adapter
    app.state.fake_adapter = fake_adapter

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as test_client:
        yield test_client

    temp_dir.cleanup()


def assert_valid_request_id(response):
    """Verify that the response contains a correctly formatted request ID."""

    request_id = response.headers["x-prism-request-id"]
    assert re.fullmatch(r"req_[0-9a-f]{8,}", request_id)
    return request_id


def test_valid_request_passes_through_to_fake_provider(client):
    """An authenticated request reaches the fake provider."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    assert_valid_request_id(response)
    assert response.headers["x-prism-provider"] == "alpha/fake-model"
    assert response.headers["x-prism-cache"] == "miss"
    assert response.headers["x-prism-fallback"] == "false"
    assert response.headers["x-prism-cost-usd"] == "0"

    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == (
        "Fake provider response"
    )
    assert body["usage"]["total_tokens"] == 15

    adapter = client.app.state.fake_adapter
    assert adapter.call_count == 1
    assert adapter.last_request == payload

    # Verify that successful provider usage was persisted.
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = client.app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_requests == 1
    assert usage.total_tokens == 15
    assert usage.total_spend_usd == 0.0


def test_calculates_non_zero_cost_and_records_actual_usage(client):
    """Cost uses provider-reported tokens and is persisted correctly."""

    # Configure non-zero pricing for the provider-returned model.
    client.app.state.loaded_config = GatewayConfig(
        model_pricing={
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=2.0,
                output_price_per_million=4.0,
            )
        }
    )

    # max_tokens is deliberately different from actual provider usage.
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Calculate actual usage"}
        ],
        "max_tokens": 1000,
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    # FakeProviderAdapter reports:
    # prompt_tokens = 10
    # completion_tokens = 5
    # total_tokens = 15
    expected_cost = ((10 * 2.0) + (5 * 4.0)) / 1_000_000

    assert expected_cost == pytest.approx(0.00004)
    assert response.headers["x-prism-cost-usd"] == "4e-05"

    # Verify the calculated cost and actual token usage in SQLite.
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = client.app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_spend_usd == pytest.approx(expected_cost)
    assert usage.total_tokens == 15
    assert usage.total_requests == 1
    assert usage.cache_hits == 0

    # Verify the provider received the original request.
    adapter = client.app.state.fake_adapter
    assert adapter.call_count == 1
    assert adapter.last_request["max_tokens"] == 1000


def test_missing_api_key_returns_401(client):
    """A request without an API key must be rejected."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["message"] == (
        "Invalid or missing API key."
    )

    assert client.app.state.fake_adapter.call_count == 0


def test_invalid_api_key_returns_401(client):
    """An invalid API key must be rejected."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": "invalid-api-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["message"] == (
        "Invalid or missing API key."
    )

    assert client.app.state.fake_adapter.call_count == 0


def test_successful_request_logs_decision_trace(client, caplog):
    """A successful request logs its completed decision trace."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    with caplog.at_level(logging.INFO, logger="prism.api.routes"):
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"x-api-key": TEST_API_KEY},
        )

    assert response.status_code == 200

    trace_records = [
        record
        for record in caplog.records
        if record.name == "prism.api.routes"
        and record.getMessage().startswith("Decision trace:")
    ]

    assert len(trace_records) == 1

    trace_record = trace_records[0]
    trace_message = trace_record.getMessage()

    assert trace_record.levelno == logging.INFO
    assert "request validation ok" in trace_message
    assert "auth ok" in trace_message
    assert "rate ok" in trace_message
    assert "provider alpha selected" in trace_message
    assert "fake-model response received" in trace_message
    assert "cost: $0.000000" in trace_message

    assert trace_record.request_id == response.headers[
        "x-prism-request-id"
    ]


def test_missing_model_returns_400(client):
    """A request without a model returns a client error."""

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == (
        "invalid_request"
    )
    assert_valid_request_id(response)

    assert client.app.state.fake_adapter.call_count == 0


def test_health_endpoint_returns_ok(client):
    """The health endpoint does not require authentication."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_valid_request_id(response)


def test_each_request_gets_a_unique_request_id(client):
    """Separate requests receive separate request IDs."""

    first_response = client.get("/health")
    second_response = client.get("/health")

    first_id = assert_valid_request_id(first_response)
    second_id = assert_valid_request_id(second_response)

    assert first_id != second_id
