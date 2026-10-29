"""Unit tests for the Prism API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import (
    AuthenticationError,
    PrismError,
    UpstreamError,
)
from prism.domain.models import VirtualKeyConfig
from tests.helpers.fake_adapter import FakeProviderAdapter


def create_test_app(adapter: FakeProviderAdapter) -> FastAPI:
    """Create a test app with all dependencies required by the routes."""

    app = FastAPI()

    # Register middleware so every request receives a request ID.
    app.middleware("http")(request_id_middleware)

    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    # Configure the clock used when creating RequestContext.
    app.state.clock = SystemClock()

    # Provide seed-key metadata for the prototype RequestContext.
    # This is test configuration, not authentication.
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
                    model_allowlist=["fake-model"],
                    cache_enabled=True,
                    cache_threshold=0.8,
                    status="active",
                )
            ]
        },
    )()

    app.state.provider_adapter = adapter

    return app


@pytest.fixture
def client():
    """Create a test client with a successful fake provider."""

    app = create_test_app(FakeProviderAdapter())

    with TestClient(app) as test_client:
        yield test_client


def valid_payload():
    """Return a valid chat completion request."""

    return {
        "model": "fake-model",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }


def test_chat_completions_returns_openai_compatible_response(client):
    """A successful request returns an OpenAI-compatible response."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
    )

    assert response.status_code == 200

    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == (
        "Fake provider response"
    )
    assert body["usage"]["total_tokens"] == 15

    # Verify the Prism response metadata headers.
    assert response.headers["x-prism-request-id"].startswith("req_")
    assert response.headers["x-prism-provider"] == "alpha/fake-model"
    assert response.headers["x-prism-cache"] == "miss"
    assert response.headers["x-prism-fallback"] == "false"
    assert response.headers["x-prism-cost-usd"] == "0"


def test_missing_model_returns_400(client):
    """A request without a model returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "x-prism-request-id" in response.headers


def test_missing_messages_returns_400(client):
    """A request without messages returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={"model": "fake-model"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "x-prism-request-id" in response.headers


def test_upstream_error_returns_502():
    """An upstream provider error returns HTTP 502."""

    app = create_test_app(
        FakeProviderAdapter(
            error=UpstreamError("Simulated provider failure")
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
        )

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_error"
    assert response.json()["error"]["code"] == 502
    assert "x-prism-request-id" in response.headers


def test_other_prism_error_uses_its_configured_status():
    """Other Prism errors retain their configured HTTP status."""

    app = create_test_app(
        FakeProviderAdapter(
            error=AuthenticationError("Invalid API key")
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
        )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid API key"
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["code"] == 401
    assert "x-prism-request-id" in response.headers
