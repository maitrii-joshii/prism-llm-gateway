import sqlite3

import pytest

from prism.adapters.sqlite_repos import (
    SQLiteKeyRepository,
    hash_api_key,
    init_database,
)
from prism.domain.models import VirtualKeyConfig


@pytest.fixture
def repository(tmp_path):
    """Create a repository using a temporary SQLite database."""

    database_path = tmp_path / "test_keys.db"
    init_database(database_path)

    return SQLiteKeyRepository(database_path)


@pytest.fixture
def sample_key():
    """Create a sample virtual key configuration."""

    raw_key = "prism-sk-search-1a2b3c"

    return VirtualKeyConfig(
        key_hash=hash_api_key(raw_key),
        tenant_id="tenant-demo",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=[
            "gpt-4o-mini",
            "llama-3.3-70b-versatile",
        ],
        cache_enabled=True,
        cache_threshold=0.8,
        status="active",
    )


def test_hash_api_key_returns_sha256_hash():
    raw_key = "prism-sk-search-1a2b3c"

    result = hash_api_key(raw_key)

    assert len(result) == 64
    assert result == (
        "7fbc3fea81e1f807fd3449f84677845"
        "ddc9e32e71d5b71cd547d6de94667fd3e"
    )


def test_seed_keys_and_retrieve_key(repository, sample_key):
    repository.seed_keys([sample_key])

    result = repository.get_by_hash(sample_key.key_hash)

    assert result is not None
    assert result.tenant_id == "tenant-demo"
    assert result.budget_usd == 100.0
    assert result.rate_limit_rpm == 60
    assert result.model_allowlist == [
        "gpt-4o-mini",
        "llama-3.3-70b-versatile",
    ]


def test_get_by_hash_returns_none_for_unknown_key(repository):
    result = repository.get_by_hash("unknown-hash")

    assert result is None


def test_seed_keys_is_idempotent(repository, sample_key):
    repository.seed_keys([sample_key])
    repository.seed_keys([sample_key])

    result = repository.get_by_hash(sample_key.key_hash)

    assert result is not None
    assert result.key_hash == sample_key.key_hash


def test_database_stores_hash_not_raw_key(
    repository,
    sample_key,
    tmp_path,
):
    raw_key = "prism-sk-search-1a2b3c"

    repository.seed_keys([sample_key])

    database_path = tmp_path / "test_keys.db"

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT key_hash FROM virtual_keys"
        ).fetchone()

    assert row is not None
    assert row[0] == sample_key.key_hash
    assert row[0] != raw_key