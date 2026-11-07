"""Unit tests for the SQLite request log repository."""

import pytest

from prism.adapters.sqlite_repos import (
    SQLiteLogRepository,
    init_database,
)
from prism.domain.models import LogEntry


@pytest.fixture
def log_repository(tmp_path):
    """Create a log repository backed by a temporary SQLite database."""

    database_path = tmp_path / "test_logs.db"
    init_database(database_path)

    return SQLiteLogRepository(database_path)


def create_log(
    request_id: str,
    key_hash: str | None = "key-hash-123",
    status_code: int = 200,
) -> LogEntry:
    """Create a reusable request log entry for tests."""

    return LogEntry(
        request_id=request_id,
        key_hash=key_hash,
        model_requested="gpt-4o-mini",
        model_resolved="gpt-4o-mini",
        provider="openai",
        status_code=status_code,
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.002,
        cache_result="miss",
        fallback_used=False,
        retries=0,
        latency_ms=250,
        decision_trace=["request_received", "provider_selected"],
    )


def test_save_and_get_log(log_repository):
    """A saved log should be retrievable by request ID."""

    log_entry = create_log("request-001")

    log_repository.save_log(log_entry)

    saved_log = log_repository.get_log("request-001")

    assert saved_log is not None
    assert saved_log.request_id == "request-001"
    assert saved_log.key_hash == "key-hash-123"
    assert saved_log.status_code == 200
    assert saved_log.prompt_tokens == 100
    assert saved_log.completion_tokens == 50
    assert saved_log.cost_usd == 0.002
    assert saved_log.decision_trace == [
        "request_received",
        "provider_selected",
    ]


def test_get_log_returns_none_for_missing_request(log_repository):
    """A missing request ID should return None."""

    result = log_repository.get_log("does-not-exist")

    assert result is None


def test_get_logs_returns_all_logs(log_repository):
    """get_logs should return all saved logs."""

    log_repository.save_log(create_log("request-001"))
    log_repository.save_log(create_log("request-002"))
    log_repository.save_log(create_log("request-003"))

    logs = log_repository.get_logs(limit=10, offset=0)

    assert len(logs) == 3


def test_get_logs_filters_by_key_hash(log_repository):
    """Logs should be filterable by virtual key hash."""

    log_repository.save_log(
        create_log("request-001", key_hash="key-A")
    )
    log_repository.save_log(
        create_log("request-002", key_hash="key-B")
    )
    log_repository.save_log(
        create_log("request-003", key_hash="key-A")
    )

    logs = log_repository.get_logs(
        limit=10,
        offset=0,
        key_hash="key-A",
    )

    assert len(logs) == 2
    assert all(log.key_hash == "key-A" for log in logs)


def test_get_logs_supports_pagination(log_repository):
    """Limit and offset should control the returned page."""

    for index in range(5):
        log_repository.save_log(
            create_log(f"request-{index:03d}")
        )

    first_page = log_repository.get_logs(
        limit=2,
        offset=0,
    )

    second_page = log_repository.get_logs(
        limit=2,
        offset=2,
    )

    assert len(first_page) == 2
    assert len(second_page) == 2

    first_ids = {log.request_id for log in first_page}
    second_ids = {log.request_id for log in second_page}

    assert first_ids.isdisjoint(second_ids)


def test_save_log_supports_rejected_request_without_key(log_repository):
    """Rejected requests can be logged without an authenticated key."""

    log_entry = create_log(
        request_id="request-401",
        key_hash=None,
        status_code=401,
    )

    log_repository.save_log(log_entry)

    saved_log = log_repository.get_log("request-401")

    assert saved_log is not None
    assert saved_log.status_code == 401
    assert saved_log.key_hash is None


def test_get_logs_rejects_invalid_limit(log_repository):
    """Limit must be a positive integer."""

    with pytest.raises(ValueError):
        log_repository.get_logs(limit=0, offset=0)


def test_get_logs_rejects_negative_offset(log_repository):
    """Offset cannot be negative."""

    with pytest.raises(ValueError):
        log_repository.get_logs(limit=10, offset=-1)


def test_save_log_rejects_non_log_entry(log_repository):
    """Only LogEntry instances should be saved."""

    with pytest.raises(TypeError):
        log_repository.save_log({"request_id": "invalid"})
