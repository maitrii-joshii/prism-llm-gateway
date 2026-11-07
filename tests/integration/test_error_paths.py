"""End-to-end integration tests for Prism error paths and request logging."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.sqlite_repos import (
    SQLiteLogRepository,
    SQLiteUsageRepository,
    hash_api_key,
    init_database,
)
from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import (
    prism_error_handler,
    unexpected_error_handler,
)
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import PrismError, UpstreamError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.domain.models import (
    GatewayConfig,
    ModelPricing,
    VirtualKeyConfig,
)
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "error-path-integration-test-key"
INVALID_API_KEY = "invalid-error-path-key"
MODEL_NAME = "gpt-4o-mini"
UNKNOWN_MODEL = "unknown-model-for-testing"

INTERNAL_SECRET = "INTERNAL_DATABASE_PASSWORD_123"


def create_test_app(
    model_allowlist=None,
    rate_limit_rpm=60,
    provider_error=False,
    budget_usd=100.0,
    unexpected_error=False,
):
    """Create a test app with SQLite usage and request log repositories."""

    app = FastAPI(title="Prism Error Path Integration Test")

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(
        app.state.clock
    )

    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "error_paths.db"

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
        tenant_id="error-path-test-tenant",
        budget_usd=budget_usd,
        rate_limit_rpm=rate_limit_rpm,
        model_allowlist=(
            model_allowlist
            if model_allowlist is not None
            else [MODEL_NAME]
        ),
        cache_enabled=False,
        cache_threshold=0.8,
        status="active",
    )

    key_repository = Mock()
    key_repository.get_by_hash.return_value = key_config

    if unexpected_error:
        key_repository.get_by_hash.side_effect = RuntimeError(
            INTERNAL_SECRET
        )

    app.state.key_repository = key_repository

    app.state.loaded_config = GatewayConfig(
        model_pricing={
            MODEL_NAME: ModelPricing(
                model_name=MODEL_NAME,
                input_price_per_million=1.0,
                output_price_per_million=2.0,
            ),
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=1.0,
                output_price_per_million=2.0,
            ),
        }
    )

    app.middleware("http")(request_id_middleware)
    app.include_router(router)

    app.add_exception_handler(
        PrismError,
        prism_error_handler,
    )
    app.add_exception_handler(
        Exception,
        unexpected_error_handler,
    )

    if provider_error:
        fake_adapter = FakeProviderAdapter(
            error=UpstreamError("Fake provider unavailable")
        )
    else:
        fake_adapter = FakeProviderAdapter()

    app.state.provider_adapter = fake_adapter
    app.state.fake_adapter = fake_adapter

    return app


def valid_payload():
    """Return a valid chat completion request."""

    return {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": "Hello, Prism!",
            }
        ],
    }


def get_saved_logs(app):
    """Retrieve saved request logs from SQLite."""

    return app.state.log_repository.get_logs(
        limit=20,
        offset=0,
    )


def assert_openai_error(response, status_code, error_type):
    """Verify the standard OpenAI-compatible error response."""

    assert response.status_code == status_code

    body = response.json()

    assert "error" in body
    assert set(body["error"].keys()) == {
        "message",
        "type",
        "code",
    }

    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    assert body["error"]["type"] == error_type
    assert body["error"]["code"] == status_code

    request_id = response.headers.get("x-prism-request-id")

    assert request_id is not None
    assert request_id.strip()

    return body["error"]


def assert_error_log(app, response, status_code):
    """Verify that an error response has a corresponding SQLite log."""

    logs = get_saved_logs(app)

    matching_logs = [
        entry
        for entry in logs
        if entry.request_id
        == response.headers.get("x-prism-request-id")
    ]

    assert len(matching_logs) == 1

    entry = matching_logs[0]

    assert entry.status_code == status_code
    assert entry.request_id == response.headers["x-prism-request-id"]
    assert entry.latency_ms is not None
    assert entry.latency_ms >= 0

    return entry


def test_successful_request_is_logged():
    """A successful request is saved with status 200 and request details."""

    app = create_test_app()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        assert response.status_code == 200

        logs = get_saved_logs(app)

        assert len(logs) == 1

        entry = logs[0]

        assert entry.status_code == 200
        assert entry.request_id
        assert entry.key_hash == hash_api_key(TEST_API_KEY)
        assert entry.model_requested == MODEL_NAME
        assert entry.model_resolved == "fake-model"
        assert entry.latency_ms is not None
        assert entry.latency_ms >= 0
        assert entry.decision_trace

        assert any(
            "completed" in item
            for item in entry.decision_trace
        )

        assert TEST_API_KEY not in str(entry.model_dump())
        assert "Hello, Prism!" not in str(entry.model_dump())

    finally:
        app.state.temp_dir.cleanup()


def test_400_invalid_request_body_is_logged():
    """A missing model is rejected with 400 and logged."""

    app = create_test_app()

    try:
        invalid_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        }

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=invalid_payload,
                headers={"x-api-key": TEST_API_KEY},
            )

        error = assert_openai_error(
            response,
            400,
            "invalid_request",
        )

        assert "model" in error["message"].lower()

        entry = assert_error_log(app, response, 400)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)
        assert any(
            "invalid_request" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_401_missing_api_key_is_logged():
    """A request without an API key is logged with status 401."""

    app = create_test_app()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
            )

        assert_openai_error(
            response,
            401,
            "authentication_error",
        )

        entry = assert_error_log(app, response, 401)

        assert entry.key_hash is None

        assert any(
            "failed" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_401_invalid_api_key_is_logged_as_hash():
    """An invalid supplied key is hashed before it is logged."""

    app = create_test_app()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": INVALID_API_KEY},
            )

        assert_openai_error(
            response,
            401,
            "authentication_error",
        )

        entry = assert_error_log(app, response, 401)

        assert entry.key_hash == hash_api_key(INVALID_API_KEY)
        assert INVALID_API_KEY not in str(entry.model_dump())

    finally:
        app.state.temp_dir.cleanup()


def test_403_model_not_allowed_is_logged():
    """A model allowlist rejection is logged with status 403."""

    app = create_test_app(
        model_allowlist=["some-other-model"],
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        assert_openai_error(
            response,
            403,
            "model_not_allowed",
        )

        entry = assert_error_log(app, response, 403)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)

        assert any(
            "failed" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_404_unknown_model_is_logged():
    """An unconfigured model is rejected with 404 and logged."""

    app = create_test_app()

    try:
        payload = valid_payload()
        payload["model"] = UNKNOWN_MODEL

        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=payload,
                headers={"x-api-key": TEST_API_KEY},
            )

        error = assert_openai_error(
            response,
            404,
            "not_found_error",
        )

        assert UNKNOWN_MODEL in error["message"]

        entry = assert_error_log(app, response, 404)

        assert entry.model_requested == UNKNOWN_MODEL
        assert entry.key_hash == hash_api_key(TEST_API_KEY)

    finally:
        app.state.temp_dir.cleanup()


def test_429_rate_limit_is_logged():
    """A rate-limited request is logged with status 429."""

    app = create_test_app(rate_limit_rpm=1)

    try:
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

        assert_openai_error(
            second_response,
            429,
            "rate_limit_exceeded",
        )

        entry = assert_error_log(app, second_response, 429)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)

        assert any(
            "failed" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_429_budget_exceeded_is_logged():
    """A request exceeding its monthly budget is logged with status 429."""

    app = create_test_app(budget_usd=0.0)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        assert_openai_error(
            response,
            429,
            "budget_exceeded",
        )

        entry = assert_error_log(app, response, 429)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)

        assert any(
            "budget" in item.lower()
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_502_provider_failure_is_logged():
    """An upstream provider failure is logged with status 502."""

    app = create_test_app(provider_error=True)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        error = assert_openai_error(
            response,
            502,
            "upstream_error",
        )

        assert "Fake provider unavailable" not in error["message"]

        entry = assert_error_log(app, response, 502)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)

        assert any(
            "failed" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()


def test_500_unexpected_exception_hides_internal_details():
    """Unexpected exceptions return generic 500 without leaking details."""

    app = create_test_app(unexpected_error=True)

    try:
        with TestClient(
            app,
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        error = assert_openai_error(
            response,
            500,
            "internal_error",
        )

        assert error["message"] == (
            "An unexpected error occurred."
        )

        response_text = response.text

        assert INTERNAL_SECRET not in response_text
        assert "Traceback" not in response_text
        assert "RuntimeError" not in response_text

        entry = assert_error_log(app, response, 500)

        assert entry.key_hash == hash_api_key(TEST_API_KEY)

        assert any(
            "internal_error" in item
            for item in entry.decision_trace
        )

    finally:
        app.state.temp_dir.cleanup()
