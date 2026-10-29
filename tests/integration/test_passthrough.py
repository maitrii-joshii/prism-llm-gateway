"""Integration tests for the Prism completion pass-through flow."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.api.error_handler import prism_error_handler
from prism.api.routes import router
from prism.domain.errors import PrismError
from tests.helpers.fake_adapter import FakeProviderAdapter


@pytest.fixture
def client():
    """Create a test application with a fake provider."""

    app = FastAPI(title="Prism Integration Test")
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    fake_adapter = FakeProviderAdapter()
    app.state.provider_adapter = fake_adapter

    # Expose the adapter so tests can verify forwarding.
    app.state.fake_adapter = fake_adapter

    # Add the same health endpoint used by the main application.
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as test_client:
        yield test_client


def test_valid_request_passes_through_to_fake_provider(client):
    """A valid request returns the fake provider's completion."""

    payload = {
        "model": "fake-model",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200

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

    # Invalid requests should not reach the provider.
    assert client.app.state.fake_adapter.call_count == 0


def test_health_endpoint_returns_ok(client):
    """The health endpoint confirms the app is running."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
