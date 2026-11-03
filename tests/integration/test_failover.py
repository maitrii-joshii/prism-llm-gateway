"""Integration tests for Prism provider failover.

Covers primary provider failure, successful backup execution,
accurate fallback headers, and failure when all providers are unavailable.
"""

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
from prism.domain.errors import PrismError, UpstreamError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.domain.models import (
    AliasConfig,
    GatewayConfig,
    ModelPricing,
    ProviderResponse,
    VirtualKeyConfig,
)
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "failover-integration-test-key"

PRIMARY_MODEL = "alpha-model"
BACKUP_MODEL = "beta-model"
MODEL_ALIAS = "test-alias"


def create_test_app(primary_error=True, backup_error=False):
    """Create a test application with primary and backup providers."""

    app = FastAPI(title="Prism Failover Integration Test")

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    # Initialize a temporary SQLite database.
    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "failover_usage.db"

    init_database(str(database_path))

    app.state.usage_repository = SQLiteUsageRepository(
        str(database_path)
    )
    app.state.temp_dir = temp_dir

    key_config = VirtualKeyConfig(
        key_hash=hash_api_key(TEST_API_KEY),
        tenant_id="failover-test-tenant",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=[
            MODEL_ALIAS,
            PRIMARY_MODEL,
            BACKUP_MODEL,
        ],
        cache_enabled=False,
        cache_threshold=0.8,
        status="active",
    )

    key_repository = Mock()
    key_repository.get_by_hash.return_value = key_config
    app.state.key_repository = key_repository

    # Configure the alias and its ordered fallback chain.
    app.state.loaded_config = GatewayConfig(
        aliases={
            MODEL_ALIAS: AliasConfig(
                alias_name=MODEL_ALIAS,
                primary_model=PRIMARY_MODEL,
                fallback_chain=[BACKUP_MODEL],
            )
        },
        model_pricing={
            PRIMARY_MODEL: ModelPricing(
                model_name=PRIMARY_MODEL,
                input_price_per_million=1.0,
                output_price_per_million=2.0,
            ),
            BACKUP_MODEL: ModelPricing(
                model_name=BACKUP_MODEL,
                input_price_per_million=1.0,
                output_price_per_million=2.0,
            ),
        },
        max_retries=0,
    )

    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    # Create primary fake provider.
    primary_adapter = FakeProviderAdapter(
        error=(
            UpstreamError("Primary provider unavailable")
            if primary_error
            else None
        )
    )

    # Create backup fake provider.
    # FakeProviderAdapter accepts either response OR error, not both.
    if backup_error:
        backup_adapter = FakeProviderAdapter(
            error=UpstreamError("Backup provider unavailable")
        )
    else:
        backup_adapter = FakeProviderAdapter(
            response=ProviderResponse(
                content="Fake provider response",
                model=BACKUP_MODEL,
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                finish_reason="stop",
                raw_response={"fake": True},
            )
        )

    # Give the adapters distinct provider names for header verification.
    primary_adapter.name = "alpha"
    backup_adapter.name = "beta"

    app.state.provider_adapters = {
        PRIMARY_MODEL: primary_adapter,
        BACKUP_MODEL: backup_adapter,
    }

    # Retain the legacy reference for compatibility.
    app.state.provider_adapter = primary_adapter

    app.state.primary_adapter = primary_adapter
    app.state.backup_adapter = backup_adapter

    return app


@pytest.fixture
def client():
    """Provide a test client with primary and backup providers."""

    app = create_test_app()

    with TestClient(app) as test_client:
        yield test_client

    app.state.temp_dir.cleanup()


def valid_payload():
    """Return a valid request using the configured model alias."""

    return {
        "model": MODEL_ALIAS,
        "messages": [
            {
                "role": "user",
                "content": "Hello, Prism!",
            }
        ],
    }


def test_failover_uses_backup_when_primary_fails():
    """The backup provider succeeds when the primary provider fails."""

    app = create_test_app(
        primary_error=True,
        backup_error=False,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        assert response.status_code == 200, response.text

        body = response.json()

        assert body["object"] == "chat.completion"
        assert body["model"] == BACKUP_MODEL
        assert body["choices"][0]["message"]["content"] == (
            "Fake provider response"
        )

        # Primary must be attempted before backup.
        assert app.state.primary_adapter.call_count == 1
        assert app.state.backup_adapter.call_count == 1

        # Verify headers identify the actual responding provider.
        assert response.headers["x-prism-fallback"] == "true"
        assert response.headers["x-prism-provider"] == (
            f"beta/{BACKUP_MODEL}"
        )

    finally:
        app.state.temp_dir.cleanup()


def test_failover_returns_502_when_all_providers_fail():
    """The gateway returns HTTP 502 when both providers fail."""

    app = create_test_app(
        primary_error=True,
        backup_error=True,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                json=valid_payload(),
                headers={"x-api-key": TEST_API_KEY},
            )

        assert response.status_code == 502, response.text

        error = response.json()["error"]

        assert error["type"] == "upstream_error"

        # Both providers must have been attempted.
        assert app.state.primary_adapter.call_count == 1
        assert app.state.backup_adapter.call_count == 1

    finally:
        app.state.temp_dir.cleanup()
