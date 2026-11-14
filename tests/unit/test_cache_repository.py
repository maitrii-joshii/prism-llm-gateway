"""Unit tests for the SQLite semantic cache repository."""

import json
import sqlite3

import pytest

from prism.adapters.sqlite_repos import (
    CacheRepository,
    init_database,
)


@pytest.fixture
def cache_repository(tmp_path):
    database_path = tmp_path / "test_cache.db"
    init_database(database_path)

    return CacheRepository(database_path)


def test_store_and_search_cache_entry(cache_repository):
    embedding = [1.0, 0.5, 0.0]
    response = {"content": "Your password has been reset."}

    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        response_body=response,
    )

    result = cache_repository.search(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        threshold=0.85,
    )

    assert result is not None
    assert result.key_hash == "team-a-key"
    assert result.alias == "fast"
    assert result.embedding == embedding
    assert result.response_body == response
    assert result.hit_count == 1


def test_team_a_cannot_access_team_b_cache(cache_repository):
    embedding = [1.0, 0.5, 0.0]

    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        response_body={"content": "Team A response"},
    )

    result = cache_repository.search(
        key_hash="team-b-key",
        alias="fast",
        embedding=embedding,
        threshold=0.85,
    )

    assert result is None


def test_cache_entries_are_isolated_by_alias(cache_repository):
    embedding = [1.0, 0.5, 0.0]

    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        response_body={"content": "Fast response"},
    )

    result = cache_repository.search(
        key_hash="team-a-key",
        alias="smart",
        embedding=embedding,
        threshold=0.85,
    )

    assert result is None


def test_embedding_is_stored_as_json(cache_repository, tmp_path):
    database_path = tmp_path / "test_cache.db"
    embedding = [1.0, 0.5, 0.25]

    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        response_body={"content": "Cached response"},
    )

    connection = sqlite3.connect(database_path)

    try:
        row = connection.execute(
            "SELECT embedding, response_body FROM cache_entries"
        ).fetchone()
    finally:
        connection.close()

    assert json.loads(row[0]) == embedding
    assert json.loads(row[1]) == {"content": "Cached response"}


def test_search_below_threshold_returns_none(cache_repository):
    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=[1.0, 0.0, 0.0],
        response_body={"content": "Cached response"},
    )

    result = cache_repository.search(
        key_hash="team-a-key",
        alias="fast",
        embedding=[0.0, 1.0, 0.0],
        threshold=0.85,
    )

    assert result is None


def test_hit_count_increments_on_each_hit(cache_repository):
    embedding = [1.0, 0.5, 0.0]

    cache_repository.store(
        key_hash="team-a-key",
        alias="fast",
        embedding=embedding,
        response_body={"content": "Cached response"},
    )

    first_result = cache_repository.search(
        "team-a-key",
        "fast",
        embedding,
        0.85,
    )

    second_result = cache_repository.search(
        "team-a-key",
        "fast",
        embedding,
        0.85,
    )

    assert first_result.hit_count == 1
    assert second_result.hit_count == 2


def test_get_stats_for_specific_key(cache_repository):
    embedding = [1.0, 0.5, 0.0]

    cache_repository.store(
        "team-a-key",
        "fast",
        embedding,
        {"content": "Team A"},
    )

    cache_repository.store(
        "team-b-key",
        "fast",
        embedding,
        {"content": "Team B"},
    )

    cache_repository.search(
        "team-a-key",
        "fast",
        embedding,
        0.85,
    )

    stats = cache_repository.get_stats("team-a-key")

    assert stats.total_entries == 1
    assert stats.total_hits == 1


def test_get_global_stats(cache_repository):
    embedding = [1.0, 0.5, 0.0]

    cache_repository.store(
        "team-a-key",
        "fast",
        embedding,
        {"content": "Team A"},
    )

    cache_repository.store(
        "team-b-key",
        "fast",
        embedding,
        {"content": "Team B"},
    )

    cache_repository.search(
        "team-a-key",
        "fast",
        embedding,
        0.85,
    )

    stats = cache_repository.get_stats()

    assert stats.total_entries == 2
    assert stats.total_hits == 1


def test_invalid_threshold_raises_error(cache_repository):
    with pytest.raises(ValueError):
        cache_repository.search(
            "team-a-key",
            "fast",
            [1.0, 0.5],
            1.5,
        )


def test_empty_key_hash_is_rejected(cache_repository):
    with pytest.raises(ValueError):
        cache_repository.store(
            "",
            "fast",
            [1.0, 0.5],
            {"content": "Response"},
        )

def test_cache_eviction_bounds_total_entries(cache_repository, monkeypatch):
    """When entries exceed MAX_CACHE_ENTRIES, the oldest are evicted."""
    monkeypatch.setattr(cache_repository, "MAX_CACHE_ENTRIES", 3)

    for i in range(5):
        cache_repository.store(
            key_hash="team-a-key",
            alias=f"alias-{i}",
            embedding=[float(i), 1.0],
            response_body={"content": f"response {i}"},
        )

    stats = cache_repository.get_stats()
    assert stats.total_entries == 3, f"Expected 3 entries due to eviction, got {stats.total_entries}"
