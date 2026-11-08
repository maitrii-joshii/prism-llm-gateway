"""Integration tests for Prism semantic response caching."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.bow_embedder import BowEmbedder
from prism.adapters.sqlite_repos import (
    CacheRepository,
    SQLiteLogRepository,
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
from prism.services.cache import CacheService
from tests.helpers.fake_adapter import FakeProviderAdapter


TEST_API_KEY = "semantic-cache-test-key"
OTHER_TEAM_API_KEY = "other-team-cache-key"


@pytest.fixture
def client():
    """Create a test application with semantic caching enabled."""

    app = FastAPI(title="Prism Semantic Cache Integration Test")

    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "semantic_cache.db"

    init_database(str(database_path))

    app.state.usage_repository = SQLiteUsageRepository(
        str(database_path)
    )
    app.state.log_repository = SQLiteLogRepository(
        str(database_path)
    )

    primary_key_config = VirtualKeyConfig(
        key_hash=hash_api_key(TEST_API_KEY),
        tenant_id="team-one",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["fake-model"],
        cache_enabled=True,
        cache_threshold=0.8,
        status="active",
    )

    other_team_key_config = VirtualKeyConfig(
        key_hash=hash_api_key(OTHER_TEAM_API_KEY),
        tenant_id="team-two",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["fake-model"],
        cache_enabled=True,
        cache_threshold=0.8,
        status="active",
    )

    key_repository = Mock()
    key_repository.get_by_hash.side_effect = lambda key_hash: {
        primary_key_config.key_hash: primary_key_config,
        other_team_key_config.key_hash: other_team_key_config,
    }.get(key_hash)

    app.state.key_repository = key_repository

    app.state.loaded_config = GatewayConfig(
        model_pricing={
            "fake-model": ModelPricing(
                model_name="fake-model",
                input_price_per_million=2.0,
                output_price_per_million=4.0,
            )
        }
    )

    cache_repository = CacheRepository(str(database_path))
    cache_service = CacheService(
        embedder=BowEmbedder(),
        repository=cache_repository,
    )

    app.state.cache_repository = cache_repository
    app.state.cache_service = cache_service

    fake_adapter = FakeProviderAdapter()
    app.state.provider_adapter = fake_adapter
    app.state.fake_adapter = fake_adapter

    with TestClient(app) as test_client:
        yield test_client

    temp_dir.cleanup()


def make_payload(prompt: str, stream: bool = False) -> dict:
    """Build a valid completion request."""

    return {
        "model": "fake-model",
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": stream,
    }


def test_repeated_prompt_returns_cached_response(client):
    """The second identical request must skip provider execution."""

    payload = make_payload("Explain how database indexing works.")

    first_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    second_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.headers["x-prism-cache"] == "miss"
    assert second_response.headers["x-prism-cache"] == "hit"

    assert second_response.headers["x-prism-cost-usd"] == "0"

    assert (
        second_response.json()["choices"][0]["message"]["content"]
        == first_response.json()["choices"][0]["message"]["content"]
    )

    assert client.app.state.fake_adapter.call_count == 1

    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage = client.app.state.usage_repository.get_usage(
        key_hash=hash_api_key(TEST_API_KEY),
        month=month,
    )

    assert usage.total_requests == 2
    assert usage.total_tokens == 30
    assert usage.cache_hits == 1


def test_similar_prompt_returns_semantic_cache_hit(client):
    """A paraphrased prompt with sufficient similarity returns a hit."""

    first_response = client.post(
        "/v1/chat/completions",
        json=make_payload("How do I reset my password?"),
        headers={"x-api-key": TEST_API_KEY},
    )

    second_response = client.post(
        "/v1/chat/completions",
        json=make_payload("Please reset the password for me."),
        headers={"x-api-key": TEST_API_KEY},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.headers["x-prism-cache"] == "miss"
    assert second_response.headers["x-prism-cache"] == "hit"

    assert client.app.state.fake_adapter.call_count == 1


def test_different_topic_returns_cache_miss(client):
    """An unrelated topic must not reuse an existing cached response."""

    first_response = client.post(
        "/v1/chat/completions",
        json=make_payload("Explain database indexing."),
        headers={"x-api-key": TEST_API_KEY},
    )

    second_response = client.post(
        "/v1/chat/completions",
        json=make_payload("Explain quantum computing."),
        headers={"x-api-key": TEST_API_KEY},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.headers["x-prism-cache"] == "miss"
    assert second_response.headers["x-prism-cache"] == "miss"

    assert client.app.state.fake_adapter.call_count == 2


def test_different_team_cannot_access_another_teams_cache(client):
    """Cache entries are isolated using the virtual key hash."""

    payload = make_payload("Explain database indexing.")

    first_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    second_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": OTHER_TEAM_API_KEY},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.headers["x-prism-cache"] == "miss"
    assert second_response.headers["x-prism-cache"] == "miss"

    assert client.app.state.fake_adapter.call_count == 2


def test_time_sensitive_prompt_skips_cache(client):
    """Time-sensitive prompts must not be stored or retrieved."""

    payload = make_payload("What's the weather now?")

    first_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    second_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.headers["x-prism-cache"] == "miss"
    assert second_response.headers["x-prism-cache"] == "miss"

    # Neither request should use a cached response.
    assert client.app.state.fake_adapter.call_count == 2


def test_streaming_request_replays_cached_response(client):
    """A cached response can be replayed as an SSE response."""

    payload = make_payload(
        "Explain what a database index is.",
        stream=False,
    )

    first_response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"x-api-key": TEST_API_KEY},
    )

    assert first_response.status_code == 200
    assert first_response.headers["x-prism-cache"] == "miss"

    streaming_payload = make_payload(
        "Explain what a database index is.",
        stream=True,
    )

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json=streaming_payload,
        headers={"x-api-key": TEST_API_KEY},
    ) as second_response:
        assert second_response.status_code == 200
        assert second_response.headers["content-type"].startswith(
            "text/event-stream"
        )
        assert second_response.headers["x-prism-cache"] == "hit"
        assert second_response.headers["x-prism-cost-usd"] == "0"

        body = second_response.read()

    assert b"Fake provider response" in body
    assert b"data: [DONE]" in body

    assert client.app.state.fake_adapter.call_count == 1
    assert client.app.state.fake_adapter.stream_call_count == 0
