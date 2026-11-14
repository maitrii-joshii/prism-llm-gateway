"""Unit tests for the Prism Admin API endpoints."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.sqlite_repos import (
    CacheRepository,
    SQLiteUsageRepository,
    SQLiteLogRepository,
    init_database,
)
from prism.api.admin import router as admin_router
from prism.api.middleware import request_id_middleware


ADMIN_TOKEN = "test-admin-token-secret"


def create_admin_test_app() -> tuple[FastAPI, str]:
    """Create a minimal FastAPI app wired with admin router and a temp DB."""

    temp_dir = TemporaryDirectory()
    database_path = str(Path(temp_dir.name) / "test_admin.db")
    init_database(database_path)

    app = FastAPI()
    app.middleware("http")(request_id_middleware)
    app.include_router(admin_router)

    app.state.usage_repository = SQLiteUsageRepository(database_path)
    app.state.log_repository = SQLiteLogRepository(database_path)
    app.state.cache_repository = CacheRepository(database_path)

    # Store temp_dir on app to prevent premature garbage collection.
    app.state._temp_dir = temp_dir

    return app, database_path


# ---------------------------------------------------------------------------
# Admin token authentication tests
# ---------------------------------------------------------------------------


def test_admin_requires_token(monkeypatch):
    """Requests without a bearer token are rejected with 401."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, _ = create_admin_test_app()

    with TestClient(app) as client:
        response = client.get("/admin/usage")

    assert response.status_code == 401


def test_admin_rejects_wrong_token(monkeypatch):
    """Requests with the wrong bearer token are rejected with 401."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, _ = create_admin_test_app()

    with TestClient(app) as client:
        response = client.get(
            "/admin/usage",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401


def test_admin_accepts_correct_token(monkeypatch):
    """Requests with the correct bearer token succeed."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, _ = create_admin_test_app()

    with TestClient(app) as client:
        response = client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Cache hit rate formula tests
# ---------------------------------------------------------------------------


def test_cache_hit_rate_is_zero_when_no_requests(monkeypatch):
    """Cache hit rate is 0.0 when there are no recorded requests."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, _ = create_admin_test_app()

    with TestClient(app) as client:
        response = client.get(
            "/admin/cache/stats",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["cache_hit_rate"] == 0.0
    assert body["total_requests_this_month"] == 0
    assert body["cache_hits_this_month"] == 0


def test_cache_hit_rate_computed_from_usage_table(monkeypatch):
    """
    Cache hit rate equals cache_hits / total_requests from the usage table.

    This test verifies the CORRECT formula. The old formula used
    total_hits / (total_hits + total_entries) which divides by the
    number of distinct cached prompts, not the number of requests.

    With 4 requests of which 2 are cache hits, the rate must be 0.5 (50%).
    """

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    key_hash = "aabbccdd" * 8  # 64-char fake hash

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    # Simulate 4 requests: 2 cache misses, then 2 cache hits.
    usage_repo.record_usage(
        key_hash=key_hash, month=month,
        cost=0.001, tokens=100, is_cache_hit=False,
    )
    usage_repo.record_usage(
        key_hash=key_hash, month=month,
        cost=0.001, tokens=100, is_cache_hit=False,
    )
    usage_repo.record_usage(
        key_hash=key_hash, month=month,
        cost=0.0, tokens=50, is_cache_hit=True,
    )
    usage_repo.record_usage(
        key_hash=key_hash, month=month,
        cost=0.0, tokens=50, is_cache_hit=True,
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/cache/stats",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()

    # 4 total requests, 2 cache hits → 0.5
    assert body["total_requests_this_month"] == 4
    assert body["cache_hits_this_month"] == 2
    assert body["cache_hit_rate"] == 0.5


def test_cache_hit_rate_is_not_entries_based(monkeypatch):
    """
    Regression test: cache_hit_rate must NOT use total_entries in denominator.

    Old (wrong) formula: total_hits / (total_hits + total_entries)
    With 2 hits and 1 cache entry: 2/(2+1) = 0.666...

    Correct formula: cache_hits / total_requests
    With 10 requests and 2 cache hits: 2/10 = 0.2
    """

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    cache_repo = CacheRepository(database_path)
    key_hash = "aabbccdd" * 8

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    # 10 total requests: 8 misses, 2 hits.
    for _ in range(8):
        usage_repo.record_usage(
            key_hash=key_hash, month=month,
            cost=0.001, tokens=100, is_cache_hit=False,
        )
    for _ in range(2):
        usage_repo.record_usage(
            key_hash=key_hash, month=month,
            cost=0.0, tokens=50, is_cache_hit=True,
        )

    # Store 1 cache entry with 2 accumulated hits recorded in the entry table.
    # (In the old formula this would have been 2/(2+1) = 0.666)
    cache_repo.store(
        key_hash=key_hash,
        alias="fast",
        embedding=[1.0, 0.0, 0.0],
        response_body={"content": "cached"},
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/cache/stats",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()

    # Must equal 2/10 = 0.2, not 2/(2+1) = 0.666
    assert body["cache_hit_rate"] == pytest.approx(0.2)
    # Also check the raw counts are exposed correctly
    assert body["total_requests_this_month"] == 10
    assert body["cache_hits_this_month"] == 2
    # total_entries from cache table is still exposed (useful for ops)
    assert body["total_entries"] == 1


def test_admin_usage_endpoint(monkeypatch):
    """GET /admin/usage returns correct monthly usage records."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    key_hash = "aabbccdd" * 8

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage_repo.record_usage(
        key_hash=key_hash, month=month,
        cost=0.005, tokens=500, is_cache_hit=False,
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["month"] == month
    assert body["total_keys"] == 1
    assert body["usage"][0]["total_requests"] == 1


def test_admin_logs_endpoint(monkeypatch):
    """GET /admin/logs returns recent request logs."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, _ = create_admin_test_app()

    with TestClient(app) as client:
        response = client.get(
            "/admin/logs",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "logs" in body
    assert body["count"] == 0

