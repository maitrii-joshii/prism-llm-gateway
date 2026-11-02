"""Tests for the SQLite monthly usage repository."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from prism.adapters.sqlite_repos import (
    SQLiteUsageRepository,
    init_database,
)


@pytest.fixture
def usage_repository(tmp_path):
    """Create a usage repository backed by a temporary database."""

    database_path = tmp_path / "usage.db"
    init_database(database_path)

    return SQLiteUsageRepository(database_path)


def test_record_usage_creates_monthly_row(usage_repository):
    usage_repository.record_usage(
        key_hash="key-1",
        month="2026-11",
        cost=0.001,
        tokens=100,
        is_cache_hit=False,
    )

    usage = usage_repository.get_usage("key-1", "2026-11")

    assert usage.key_hash == "key-1"
    assert usage.month == "2026-11"
    assert usage.total_spend_usd == pytest.approx(0.001)
    assert usage.total_tokens == 100
    assert usage.total_requests == 1
    assert usage.cache_hits == 0


def test_record_usage_increments_existing_row(usage_repository):
    usage_repository.record_usage(
        "key-1", "2026-11", 0.001, 100, False
    )
    usage_repository.record_usage(
        "key-1", "2026-11", 0.002, 200, True
    )

    usage = usage_repository.get_usage("key-1", "2026-11")

    assert usage.total_spend_usd == pytest.approx(0.003)
    assert usage.total_tokens == 300
    assert usage.total_requests == 2
    assert usage.cache_hits == 1


def test_new_month_creates_separate_row(usage_repository):
    """A new month starts with zero usage and preserves previous data."""

    # Record usage in October.
    usage_repository.record_usage(
        "key-1", "2026-10", 0.005, 500, False
    )

    # Before recording anything in November, verify fresh counters.
    november = usage_repository.get_usage("key-1", "2026-11")

    assert november.total_spend_usd == 0.0
    assert november.total_tokens == 0
    assert november.total_requests == 0
    assert november.cache_hits == 0

    # Record usage in November.
    usage_repository.record_usage(
        "key-1", "2026-11", 0.002, 200, False
    )

    # Fetch both months.
    october = usage_repository.get_usage("key-1", "2026-10")
    november = usage_repository.get_usage("key-1", "2026-11")

    # October data must remain unchanged.
    assert october.total_spend_usd == pytest.approx(0.005)
    assert october.total_tokens == 500
    assert october.total_requests == 1
    assert october.cache_hits == 0

    # November contains only its own usage.
    assert november.total_spend_usd == pytest.approx(0.002)
    assert november.total_tokens == 200
    assert november.total_requests == 1
    assert november.cache_hits == 0


def test_missing_usage_returns_zero_totals(usage_repository):
    usage = usage_repository.get_usage("unknown-key", "2026-11")

    assert usage.total_spend_usd == 0.0
    assert usage.total_tokens == 0
    assert usage.total_requests == 0
    assert usage.cache_hits == 0


def test_get_all_usage_returns_only_requested_month(
    usage_repository,
):
    usage_repository.record_usage(
        "key-1", "2026-10", 0.001, 100, False
    )
    usage_repository.record_usage(
        "key-1", "2026-11", 0.002, 200, False
    )
    usage_repository.record_usage(
        "key-2", "2026-11", 0.003, 300, True
    )

    usages = usage_repository.get_all_usage("2026-11")

    assert len(usages) == 2
    assert {usage.key_hash for usage in usages} == {"key-1", "key-2"}


def test_concurrent_updates_do_not_lose_data(usage_repository):
    number_of_updates = 20

    def record_one_update(_):
        usage_repository.record_usage(
            key_hash="key-concurrent",
            month="2026-11",
            cost=0.001,
            tokens=10,
            is_cache_hit=False,
        )

    with ThreadPoolExecutor(max_workers=number_of_updates) as executor:
        list(executor.map(record_one_update, range(number_of_updates)))

    usage = usage_repository.get_usage(
        "key-concurrent",
        "2026-11",
    )

    assert usage.total_requests == number_of_updates
    assert usage.total_tokens == number_of_updates * 10
    assert usage.total_spend_usd == pytest.approx(
        number_of_updates * 0.001
    )


def test_rejects_negative_cost(usage_repository):
    with pytest.raises(ValueError):
        usage_repository.record_usage(
            "key-1", "2026-11", -0.001, 100, False
        )


def test_rejects_negative_tokens(usage_repository):
    with pytest.raises(ValueError):
        usage_repository.record_usage(
            "key-1", "2026-11", 0.001, -100, False
        )


def test_rejects_invalid_cache_hit_value(usage_repository):
    with pytest.raises(ValueError):
        usage_repository.record_usage(
            "key-1", "2026-11", 0.001, 100, 1
        )
