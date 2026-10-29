"""Integration tests for the Prism completion pass-through flow."""

import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import PrismError
from prism.domain.models import VirtualKeyConfig
from tests.helpers.fake_adapter import FakeProviderAdapter


@pytest.fixture
def client():
    """Create a test application with a fake provider."""

    app = FastAPI(title="Prism Integration Test")

    # Configure the dependencies required by RequestContext.
    app.state.clock = SystemClock()
    app.state.config = type(
        "TestConfig",
        (),
        {
            "seed_keys": [
                VirtualKeyConfig(
                    key_hash="test-hash",
                    tenant_id="test-tenant",
                    budget_usd=100.0,
                    rate_limit_rpm=60,
                    model_allowlist=["gpt-4o-mini"],
                    cache_enabled=True,
                    cache_threshold=0.8,
                    status="active",
                )
            ]
        },
    )()

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


def assert_valid_request_id(response):
    """Verify that the response contains a correctly formatted request ID."""

    request_id = response.headers["x-prism-request-id"]
    assert re.fullmatch(r"req_[0-9a-f]{8,}", request_id)
    return request_id


def test_valid_request_passes_through_to_fake_provider(client):
    """A valid request returns the fake provider's completion."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200

    # Verify all five custom response headers.
    assert_valid_request_id(response)
    assert response.headers["x-prism-provider"] == "alpha/fake-model"
    assert response.headers["x-prism-cache"] == "miss"
    assert response.headers["x-prism-fallback"] == "false"
    assert response.headers["x-prism-cost-usd"] == "0"

    # Verify the existing OpenAI-compatible response body.
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == (
        "Fake provider response"
    )
    assert body["usage"]["total_tokens"] == 15

    # Verify that the request reached the fake provider.
    adapter = client.app.state.fake_adapter
    assert adapter.call_count == 1
    assert adapter.last_request == payload


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
    assert "provider alpha selected" in trace_message
    assert "fake-model response received" in trace_message

    # The trace must be associated with the same request as the response.
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
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == (
        "invalid_request_error"
    )
    assert_valid_request_id(response)

    # Invalid requests should not reach the provider.
    assert client.app.state.fake_adapter.call_count == 0


def test_health_endpoint_returns_ok(client):
    """The health endpoint confirms that the app is running."""

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
