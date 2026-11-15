"""Unit tests for the Prism Admin API and AdminService."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

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
from prism.services.admin import AdminService


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

    app.state._temp_dir = temp_dir

    return app, database_path


# ---------------------------------------------------------------------------
# AdminService test helpers
# ---------------------------------------------------------------------------


class FakeCacheRepository:
    """Fake cache repository for AdminService unit tests."""

    def __init__(self, stats):
        self.stats = stats

    def get_stats(self):
        return self.stats


class FakeUsageRepository:
    """Fake usage repository for AdminService unit tests."""

    def __init__(self, records):
        self.records = records
        self.requested_month = None

    def get_all_usage(self, month):
        self.requested_month = month
        return self.records


def create_usage_record(
    total_requests: int,
    cache_hits: int,
):
    """Create a lightweight usage record for service tests."""

    return SimpleNamespace(
        total_requests=total_requests,
        cache_hits=cache_hits,
    )


def create_admin_service(usage_records):
    """Create AdminService with fake repositories."""

    cache_stats = SimpleNamespace(
        total_entries=5,
        total_hits=12,
    )

    cache_repository = FakeCacheRepository(cache_stats)
    usage_repository = FakeUsageRepository(usage_records)

    service = AdminService(
        cache_repository=cache_repository,
        usage_repository=usage_repository,
    )

    return service, cache_stats, usage_repository


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
# AdminService unit tests
# ---------------------------------------------------------------------------


def test_admin_service_aggregates_usage_across_multiple_keys():
    """Cache statistics aggregate usage from multiple virtual keys."""

    usage_records = [
        create_usage_record(total_requests=4, cache_hits=2),
        create_usage_record(total_requests=6, cache_hits=1),
    ]

    service, cache_stats, usage_repository = create_admin_service(
        usage_records
    )

    result = service.get_cache_statistics()

    assert result.stats is cache_stats
    assert result.total_requests_this_month == 10
    assert result.cache_hits_this_month == 3
    assert result.cache_hit_rate == 0.3

    assert usage_repository.requested_month is not None
    assert len(usage_repository.requested_month) == 7


def test_admin_service_returns_zero_hit_rate_when_no_requests():
    """Cache hit rate is zero when there are no usage records."""

    service, cache_stats, _ = create_admin_service([])

    result = service.get_cache_statistics()

    assert result.stats is cache_stats
    assert result.total_requests_this_month == 0
    assert result.cache_hits_this_month == 0
    assert result.cache_hit_rate == 0.0


def test_admin_service_rounds_hit_rate_to_four_decimal_places():
    """Cache hit rate is rounded to four decimal places."""

    usage_records = [
        create_usage_record(total_requests=3, cache_hits=1),
    ]

    service, _, _ = create_admin_service(usage_records)

    result = service.get_cache_statistics()

    assert result.cache_hit_rate == 0.3333


def test_admin_service_preserves_cache_repository_statistics():
    """Cache entry statistics are returned from the cache repository."""

    usage_records = [
        create_usage_record(total_requests=10, cache_hits=4),
    ]

    service, cache_stats, _ = create_admin_service(usage_records)

    result = service.get_cache_statistics()

    assert result.stats is cache_stats
    assert result.stats.total_entries == 5
    assert result.stats.total_hits == 12


# ---------------------------------------------------------------------------
# Cache hit rate API tests
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
    """Cache hit rate equals cache_hits / total_requests."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    key_hash = "aabbccdd" * 8

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    for is_cache_hit in [False, False, True, True]:
        usage_repo.record_usage(
            key_hash=key_hash,
            month=month,
            cost=0.0 if is_cache_hit else 0.001,
            tokens=50 if is_cache_hit else 100,
            is_cache_hit=is_cache_hit,
        )

    with TestClient(app) as client:
        response = client.get(
            "/admin/cache/stats",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )

    assert response.status_code == 200
    body = response.json()

    assert body["total_requests_this_month"] == 4
    assert body["cache_hits_this_month"] == 2
    assert body["cache_hit_rate"] == 0.5


def test_cache_hit_rate_is_not_entries_based(monkeypatch):
    """Cache hit rate must use total requests, not cache entries."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    cache_repo = CacheRepository(database_path)
    key_hash = "aabbccdd" * 8

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    for _ in range(8):
        usage_repo.record_usage(
            key_hash=key_hash,
            month=month,
            cost=0.001,
            tokens=100,
            is_cache_hit=False,
        )

    for _ in range(2):
        usage_repo.record_usage(
            key_hash=key_hash,
            month=month,
            cost=0.0,
            tokens=50,
            is_cache_hit=True,
        )

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

    assert body["cache_hit_rate"] == pytest.approx(0.2)
    assert body["total_requests_this_month"] == 10
    assert body["cache_hits_this_month"] == 2
    assert body["total_entries"] == 1


# ---------------------------------------------------------------------------
# Admin endpoint tests
# ---------------------------------------------------------------------------


def test_admin_usage_endpoint(monkeypatch):
    """GET /admin/usage returns correct monthly usage records."""

    monkeypatch.setenv("PRISM_ADMIN_TOKEN", ADMIN_TOKEN)
    app, database_path = create_admin_test_app()

    usage_repo = SQLiteUsageRepository(database_path)
    key_hash = "aabbccdd" * 8

    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    usage_repo.record_usage(
        key_hash=key_hash,
        month=month,
        cost=0.005,
        tokens=500,
        is_cache_hit=False,
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
