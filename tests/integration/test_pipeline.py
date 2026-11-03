"""Integration tests for the Prism request pipeline."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.sqlite_repos import SQLiteUsageRepository, init_database
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
from prism.domain.security import hash_api_key
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "pipeline-integration-test-key"


def create_test_client(
    key_status: str = "active",
    rate_limit_rpm: int = 60,
):
    """Create a test application with a fake provider and virtual key."""

    app = FastAPI(title="Prism Pipeline Integration Test")

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
        tenant_id="pipeline-test-tenant",
        budget_usd=100.0,
        rate_limit_rpm=rate_limit_rpm,
        model_allowlist=["gpt-4o-mini"],
        cache_enabled=True,
        cache_threshold=0.8,
        status=key_status,
    )

    key_repository = Mock()
    key_repository.get_by_hash.return_value = key_config

    app.state.key_repository = key_repository

    # Configure pricing for both the requested model and
    # the model returned by the fake provider.
    app.state.loaded_config = GatewayConfig(
        model_pricing={
            "gpt-4o-mini": ModelPricing(
                model_name="gpt-4o-mini",
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            ),
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            ),
        }
    )

    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    fake_adapter = FakeProviderAdapter()

    app.state.provider_adapter = fake_adapter
    app.state.fake_adapter = fake_adapter

    return app


@pytest.fixture
def client():
    """Provide a test client with an active virtual key."""

    app = create_test_client()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def disabled_key_client():
    """Provide a test client with a disabled virtual key."""

    app = create_test_client(key_status="disabled")

    with TestClient(app) as test_client:
        yield test_client


def valid_payload():
    """Return a valid chat completion request."""

    return {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": "Hello, Prism!",
            }
        ],
    }


def test_pipeline_happy_path_calls_fake_provider(client):
    """A valid authenticated request reaches the fake provider."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["object"] == "chat.completion"
    assert body["model"] == "fake-model"
    assert body["choices"][0]["message"]["content"] == (
        "Fake provider response"
    )

    adapter = client.app.state.fake_adapter

    assert adapter.call_count == 1
    assert adapter.last_request == valid_payload()


# -------------------------------------------------------------------
# Rate limiting tests
# -------------------------------------------------------------------


def test_pipeline_rejects_request_when_rate_limit_is_exceeded():
    """The pipeline returns HTTP 429 after the RPM limit is reached."""

    app = create_test_client(rate_limit_rpm=1)

    with TestClient(app) as client:
        headers = {"x-api-key": TEST_API_KEY}

        first_response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
            headers=headers,
        )

        second_response = client.post(
            "/v1/chat/completions",
            json=valid_payload(),
            headers=headers,
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429

    error_body = second_response.json()["error"]

    assert error_body["type"] == "rate_limit_exceeded"
    assert "message" in error_body
    assert isinstance(error_body["message"], str)
    assert error_body["message"]

    assert app.state.fake_adapter.call_count == 1


# -------------------------------------------------------------------
# Authentication tests
# -------------------------------------------------------------------


def test_pipeline_rejects_missing_api_key(client):
    """The pipeline rejects a request without an API key."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == (
        "authentication_error"
    )

    assert client.app.state.fake_adapter.call_count == 0


def test_pipeline_rejects_invalid_api_key(client):
    """The pipeline rejects an invalid API key."""

    response = client.post(
        "/v1/chat/completions",
        json=valid_payload(),
        headers={"x-api-key": "invalid-api-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == (
        "authentication_error"
    )

    assert client.app.state.fake_adapter.call_count == 0


def test_pipeline_rejects_disabled_api_key(disabled_key_client):
    """The pipeline rejects a disabled virtual key."""

    response = disabled_key_client.post(
        "/v1/chat/completions",
        json=valid_payload(),
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == (
        "authentication_error"
    )

    assert disabled_key_client.app.state.fake_adapter.call_count == 0


def test_pipeline_rejects_missing_model(client):
    """The pipeline rejects a request without a model."""

    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Hello, Prism!",
            }
        ]
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"

    assert client.app.state.fake_adapter.call_count == 0


def test_pipeline_rejects_empty_messages(client):
    """The pipeline rejects an empty messages list."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [],
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"

    assert client.app.state.fake_adapter.call_count == 0


def test_pipeline_rejects_invalid_max_tokens(client):
    """The pipeline rejects invalid max_tokens."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": "Hello, Prism!",
            }
        ],
        "max_tokens": -1,
    }

    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"

    assert client.app.state.fake_adapter.call_count == 0
