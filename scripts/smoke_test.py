"""End-to-end smoke tests for the Prism LLM Gateway.

Uses real FastAPI routes, temporary SQLite storage, and fake providers.
No external provider API keys or network calls are required.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

# Make project root importable when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.bow_embedder import BowEmbedder
from prism.adapters.sqlite_repos import (
    CacheRepository,
    SQLiteKeyRepository,
    SQLiteLogRepository,
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
from prism.services.cache import CacheService
from tests.helpers.fake_adapter import FakeProviderAdapter


FAST_MODEL = "gpt-4o-mini"
SMART_MODEL = "llama-3.3-70b-versatile"

FAST_KEY = "smoke-test-fast-key"
RATE_KEY = "smoke-test-rate-key"
BUDGET_KEY = "smoke-test-budget-key"

API_URL = "/v1/chat/completions"


def make_key(api_key, budget=100.0, rpm=60):
    """Create a virtual key configuration."""

    return VirtualKeyConfig(
        key_hash=hash_api_key(api_key),
        tenant_id="smoke-test-tenant",
        budget_usd=budget,
        rate_limit_rpm=rpm,
        model_allowlist=[
            "fast",
            "smart",
            "auto",
            FAST_MODEL,
            SMART_MODEL,
        ],
        cache_enabled=True,
        cache_threshold=0.85,
        status="active",
    )


def make_response(model):
    """Create a successful fake provider response."""

    return ProviderResponse(
        content=f"Smoke test response from {model}",
        model=model,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
        raw_response={"smoke_test": True},
    )


def create_app(primary_error=False, backup_error=False):
    """Create an isolated Prism application for smoke testing."""

    temp_dir = TemporaryDirectory()
    database_path = Path(temp_dir.name) / "smoke_test.db"

    init_database(str(database_path))

    app = FastAPI(title="Prism Smoke Test")

    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    app.state.temp_dir = temp_dir
    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(
        app.state.clock
    )

    app.state.key_repository = SQLiteKeyRepository(
        str(database_path)
    )

    app.state.usage_repository = SQLiteUsageRepository(
        str(database_path)
    )

    app.state.log_repository = SQLiteLogRepository(
        str(database_path)
    )

    app.state.cache_repository = CacheRepository(
        str(database_path)
    )

    app.state.cache_service = CacheService(
        embedder=BowEmbedder(),
        repository=app.state.cache_repository,
    )

    app.state.key_repository.seed_keys([
        make_key(FAST_KEY),
        make_key(RATE_KEY, rpm=1),
        make_key(BUDGET_KEY, budget=0.01),
    ])

    app.state.loaded_config = GatewayConfig(
        aliases={
            "fast": AliasConfig(
                alias_name="fast",
                primary_model=FAST_MODEL,
                fallback_chain=[SMART_MODEL],
            ),
            "smart": AliasConfig(
                alias_name="smart",
                primary_model=SMART_MODEL,
                fallback_chain=[FAST_MODEL],
            ),
        },
        model_pricing={
            FAST_MODEL: ModelPricing(
                model_name=FAST_MODEL,
                input_price_per_million=0.15,
                output_price_per_million=0.60,
            ),
            SMART_MODEL: ModelPricing(
                model_name=SMART_MODEL,
                input_price_per_million=0.59,
                output_price_per_million=0.79,
            ),
        },
        max_retries=0,
    )

    primary_adapter = FakeProviderAdapter(
        response=make_response(FAST_MODEL)
        if not primary_error
        else None,
        error=(
            UpstreamError("Primary provider unavailable")
            if primary_error
            else None
        ),
    )

    backup_adapter = FakeProviderAdapter(
        response=make_response(SMART_MODEL)
        if not backup_error
        else None,
        error=(
            UpstreamError("Backup provider unavailable")
            if backup_error
            else None
        ),
    )

    primary_adapter.name = "alpha"
    backup_adapter.name = "beta"

    app.state.provider_adapters = {
        FAST_MODEL: primary_adapter,
        SMART_MODEL: backup_adapter,
    }

    app.state.provider_adapter = primary_adapter
    app.state.primary_adapter = primary_adapter
    app.state.backup_adapter = backup_adapter

    return app


def make_payload(prompt, model="fast", stream=False):
    """Build a valid chat completion request."""

    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": stream,
    }


def post(client, payload, api_key=FAST_KEY):
    """Send an authenticated completion request."""

    return client.post(
        API_URL,
        json=payload,
        headers={"x-api-key": api_key},
    )


def check_authentication(client, app):
    """Check missing and invalid API keys."""

    payload = make_payload("Hello Prism")

    missing = client.post(API_URL, json=payload)
    assert missing.status_code == 401, missing.text

    invalid = client.post(
        API_URL,
        json=payload,
        headers={"x-api-key": "invalid-smoke-key"},
    )

    assert invalid.status_code == 401, invalid.text
    assert app.state.primary_adapter.call_count == 0

    print("[PASS] Authentication: missing and invalid keys rejected")


def check_rate_limit(client, app):
    """Check that the RPM limit is enforced."""

    payload = make_payload("Check rate limiting")

    first = post(client, payload, RATE_KEY)
    second = post(client, payload, RATE_KEY)

    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text

    assert second.json()["error"]["type"] == "rate_limit_exceeded"

    print("[PASS] Rate limiting: second request rejected")


def check_budget(client, app):
    """Check that exhausted monthly budgets are rejected."""

    key_hash = hash_api_key(BUDGET_KEY)
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    app.state.usage_repository.record_usage(
        key_hash=key_hash,
        month=month,
        cost=0.01,
        tokens=10,
        is_cache_hit=False,
    )

    response = post(
        client,
        make_payload("Check budget enforcement"),
        BUDGET_KEY,
    )

    assert response.status_code == 429, response.text
    assert response.json()["error"]["type"] == "budget_exceeded"

    print("[PASS] Budget enforcement: exhausted budget rejected")


def check_model_resolution(client, app):
    """Check fast, smart, and automatic model resolution."""

    fast = post(
        client,
        make_payload("Hello, how are you?", model="fast"),
    )

    assert fast.status_code == 200, fast.text
    assert fast.json()["model"] == FAST_MODEL

    smart = post(
        client,
        make_payload(
            "Compare and contrast distributed monolith and "
            "microservices architectures, explain their tradeoffs, "
            "and design a scalable architecture.",
            model="smart",
        ),
    )

    assert smart.status_code == 200, smart.text
    assert smart.json()["model"] == SMART_MODEL

    automatic = post(
        client,
        make_payload(
            "Compare and contrast distributed monolith and "
            "microservices architectures, explain their tradeoffs, "
            "and design a scalable architecture.",
            model="auto",
        ),
    )

    assert automatic.status_code == 200, automatic.text
    assert automatic.json()["model"] == SMART_MODEL

    print("[PASS] Model resolution: fast, smart, and auto")


def check_streaming(client, app):
    """Check streaming response behavior."""

    payload = make_payload(
        "Explain streaming in simple terms.",
        model="fast",
        stream=True,
    )

    with client.stream(
        "POST",
        API_URL,
        json=payload,
        headers={"x-api-key": FAST_KEY},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )
        body = response.read()

    assert b"data:" in body, "No SSE data chunks received."
    assert b"[DONE]" in body, "Missing SSE completion marker."
    assert b'"content"' in body, "No streamed content chunks received."

    assert app.state.primary_adapter.stream_call_count == 1

    print("[PASS] Streaming: SSE chunks and completion marker received")


def check_semantic_cache(client, app):
    """Check that a paraphrased prompt returns a cache hit."""

    first = post(
        client,
        make_payload("How do I reset my password?"),
    )

    second = post(
        client,
        make_payload("Please reset the password for me."),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    assert first.headers["x-prism-cache"] == "miss"
    assert second.headers["x-prism-cache"] == "hit"
    assert second.headers["x-prism-cost-usd"] == "0"

    # Expected provider calls:
    # 1. First rate-limit request
    # 2. Fast model request
    # 3. Smart model request
    # 4. Auto model request
    # 5. First semantic-cache request
    total_provider_calls = (
        app.state.primary_adapter.call_count
        + app.state.backup_adapter.call_count
    )

    assert total_provider_calls == 5, (
        "Unexpected provider call count: "
        f"{total_provider_calls}"
    )

    print("[PASS] Semantic cache: paraphrased prompt returned a hit")


def check_failover():
    """Check that a backup provider is used when primary fails."""

    app = create_app(primary_error=True)

    try:
        with TestClient(app) as client:
            response = post(
                client,
                make_payload("Test provider failover"),
            )

        assert response.status_code == 200, response.text
        assert response.json()["model"] == SMART_MODEL

        assert app.state.primary_adapter.call_count == 1
        assert app.state.backup_adapter.call_count == 1

        assert response.headers["x-prism-fallback"] == "true"

        # The gateway derives provider names from model prefixes:
        # gpt-* -> openai, llama-* -> groq.
        assert response.headers["x-prism-provider"] == (
            f"groq/{SMART_MODEL}"
        )

        print("[PASS] Failover: backup provider successfully used")

    finally:
        app.state.temp_dir.cleanup()


def check_logs_and_database(app):
    """Check that requests and cache entries are persisted."""

    key_hash = hash_api_key(FAST_KEY)

    logs = app.state.log_repository.get_logs(
        limit=100,
        offset=0,
        key_hash=key_hash,
    )

    assert logs, "No request logs were persisted."

    usage = app.state.usage_repository.get_usage(
        key_hash=key_hash,
        month=datetime.now(timezone.utc).strftime("%Y-%m"),
    )

    assert usage.total_requests > 0

    cache_stats = app.state.cache_repository.get_stats(
        key_hash=key_hash
    )

    assert cache_stats.total_entries > 0

    print(
        "[PASS] Persistence: request logs, usage, and cache entries"
    )


def main():
    """Run the complete smoke test suite."""

    print("\n========== PRISM SMOKE TEST ==========\n")

    app = create_app()

    try:
        with TestClient(app) as client:
            check_authentication(client, app)
            check_rate_limit(client, app)
            check_budget(client, app)
            check_model_resolution(client, app)
            check_streaming(client, app)
            check_semantic_cache(client, app)

        check_logs_and_database(app)

    finally:
        app.state.temp_dir.cleanup()

    check_failover()

    print("\n========== ALL SMOKE TESTS PASSED ==========\n")


if __name__ == "__main__":
    main()
