import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.api.error_handler import prism_error_handler
from prism.api.routes import router
from prism.domain.errors import (
    AuthenticationError,
    PrismError,
    UpstreamError,
)
from tests.helpers.fake_adapter import FakeProviderAdapter


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)
    app.state.provider_adapter = FakeProviderAdapter()

    with TestClient(app) as test_client:
        yield test_client


def valid_payload():
    return {
        "model": "fake-model",
        "messages": [
            {"role": "user", "content": "Hello, Prism!"}
        ],
    }


def test_chat_completions_returns_openai_compatible_response(client):
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


def test_missing_model_returns_400(client):
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_missing_messages_returns_400(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "fake-model"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_upstream_error_returns_502():
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)
    app.state.provider_adapter = FakeProviderAdapter(
        error=UpstreamError("Simulated provider failure")
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
        )

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_error"
    assert response.json()["error"]["code"] == 502


def test_other_prism_error_uses_its_configured_status():
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)
    app.state.provider_adapter = FakeProviderAdapter(
        error=AuthenticationError("Invalid API key")
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
