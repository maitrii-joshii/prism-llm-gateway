"""Unit tests for the Prism API routes."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.domain.security import hash_api_key
from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import (
    AuthenticationError,
    InvalidRequestError,
    PrismError,
    UpstreamError,
)
from prism.domain.models import VirtualKeyConfig
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "test-api-key"


def create_test_app(
    adapter: FakeProviderAdapter,
    key_status: str = "active",
) -> FastAPI:
    """Create a test app with all dependencies required by the routes."""

    app = FastAPI()

    app.middleware("http")(request_id_middleware)

    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    app.state.clock = SystemClock()

    key_config = VirtualKeyConfig(
        key_hash=hash_api_key(TEST_API_KEY),
        tenant_id="test-tenant",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["fake-model"],
        cache_enabled=True,
        cache_threshold=0.8,
        status=key_status,
    )

    key_repository = Mock()
    key_repository.get_by_hash.return_value = key_config

    app.state.key_repository = key_repository
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


# -------------------------------------------------------------------
# Successful request tests
# -------------------------------------------------------------------


def test_chat_completions_returns_openai_compatible_response(client):
    """A successful authenticated request returns an OpenAI response."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
        headers={"x-api-key": TEST_API_KEY},
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

    assert response.headers["x-prism-request-id"].startswith("req_")
    assert response.headers["x-prism-provider"] == "alpha/fake-model"
    assert response.headers["x-prism-cache"] == "miss"
    assert response.headers["x-prism-fallback"] == "false"
    assert response.headers["x-prism-cost-usd"] == "0"


# -------------------------------------------------------------------
# Authentication tests
# -------------------------------------------------------------------


def test_missing_api_key_returns_401():
    """A request without an API key must return HTTP 401."""

    adapter = FakeProviderAdapter()
    app = create_test_app(adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
        )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["message"] == (
        "Invalid or missing API key."
    )
    assert adapter.call_count == 0


def test_invalid_api_key_returns_401(client):
    """An unknown API key must return HTTP 401."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
        headers={"x-api-key": "invalid-api-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["message"] == (
        "Invalid or missing API key."
    )
    assert client.app.state.provider_adapter.call_count == 0


def test_disabled_api_key_returns_401():
    """A disabled API key must return HTTP 401."""

    adapter = FakeProviderAdapter()
    app = create_test_app(adapter, key_status="disabled")

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
            headers={"x-api-key": TEST_API_KEY},
        )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["message"] == (
        "Invalid or missing API key."
    )
    assert adapter.call_count == 0


# -------------------------------------------------------------------
# Request validation tests
# -------------------------------------------------------------------


def test_missing_model_returns_400(client):
    """A request without a model returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"
    assert "x-prism-request-id" in response.headers


def test_empty_model_returns_400(client):
    """An empty model returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "   ",
            "messages": [{"role": "user", "content": "Hello"}],
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_missing_messages_returns_400(client):
    """A request without messages returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={"model": "fake-model"},
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"
    assert "x-prism-request-id" in response.headers


def test_empty_messages_returns_400(client):
    """An empty messages array returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-model",
            "messages": [],
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_message_missing_role_returns_400(client):
    """A message without role returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-model",
            "messages": [{"content": "Hello"}],
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_message_missing_content_returns_400(client):
    """A message without content returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "fake-model",
            "messages": [{"role": "user"}],
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_negative_max_tokens_returns_400(client):
    """Negative max_tokens returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            **valid_payload(),
            "max_tokens": -1,
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_zero_max_tokens_returns_400(client):
    """Zero max_tokens returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            **valid_payload(),
            "max_tokens": 0,
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_non_integer_max_tokens_returns_400(client):
    """A decimal max_tokens value returns HTTP 400."""

    response = client.post(
        "/v1/chat/completions",
        json={
            **valid_payload(),
            "max_tokens": 10.5,
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


def test_max_tokens_above_cap_is_capped(client, monkeypatch):
    """A max_tokens value above the configured cap is reduced."""

    monkeypatch.setenv("PRISM_MAX_TOKENS_CAP", "2048")

    response = client.post(
        "/v1/chat/completions",
        json={
            **valid_payload(),
            "max_tokens": 10000000,
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    adapter = client.app.state.provider_adapter

    assert adapter.last_request["max_tokens"] == 2048


def test_max_tokens_below_cap_is_unchanged(client, monkeypatch):
    """A max_tokens value below the cap remains unchanged."""

    monkeypatch.setenv("PRISM_MAX_TOKENS_CAP", "2048")

    response = client.post(
        "/v1/chat/completions",
        json={
            **valid_payload(),
            "max_tokens": 100,
        },
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    adapter = client.app.state.provider_adapter

    assert adapter.last_request["max_tokens"] == 100


# -------------------------------------------------------------------
# Provider error tests
# -------------------------------------------------------------------


def test_upstream_error_returns_502():
    """An upstream provider error returns HTTP 502."""

    adapter = FakeProviderAdapter(
        error=UpstreamError("Simulated provider failure")
    )
    app = create_test_app(adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
            headers={"x-api-key": TEST_API_KEY},
        )

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_error"
    assert response.json()["error"]["code"] == 502
    assert "x-prism-request-id" in response.headers


def test_other_prism_error_uses_its_configured_status():
    """Other Prism errors retain their configured HTTP status."""

    adapter = FakeProviderAdapter(
        error=AuthenticationError("Invalid API key")
    )
    app = create_test_app(adapter)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
            headers={"x-api-key": TEST_API_KEY},
        )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid API key"
    assert response.json()["error"]["type"] == "authentication_error"
    assert response.json()["error"]["code"] == 401
    assert "x-prism-request-id" in response.headers
