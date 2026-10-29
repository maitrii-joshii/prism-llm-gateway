"""Tests for SQLite database initialization and schema creation."""

import sqlite3

from prism.adapters.sqlite_repos import (
    get_connection,
    init_database,
)


EXPECTED_COLUMNS = {
    "virtual_keys": [
        "key_hash",
        "tenant_id",
        "budget_usd",
        "rate_limit_rpm",
        "allowlist",
        "cache_enabled",
        "cache_threshold",
        "status",
    ],
    "usage": [
        "key_hash",
        "month",
        "total_spend_usd",
        "total_tokens",
        "total_requests",
        "cache_hits",
    ],
    "request_logs": [
        "request_id",
        "key_hash",
        "model_requested",
        "model_resolved",
        "provider",
        "status_code",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "cache_result",
        "fallback_used",
        "retries",
        "latency_ms",
        "decision_trace",
        "created_at",
    ],
    "cache_entries": [
        "id",
        "key_hash",
        "alias",
        "prompt_hash",
        "embedding",
        "response_body",
        "hit_count",
        "created_at",
    ],
}


def test_database_file_and_tables_are_created(tmp_path):
    """Initialization should create a database and all four tables."""

    database_path = tmp_path / "test.db"

    init_database(database_path)

    assert database_path.is_file()

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        assert set(EXPECTED_COLUMNS).issubset(tables)
    finally:
        connection.close()


def test_all_tables_have_expected_columns(tmp_path):
    """Every application table should have the expected columns."""

    database_path = tmp_path / "test.db"
    init_database(database_path)

    connection = sqlite3.connect(database_path)
    try:
        for table_name, expected_columns in EXPECTED_COLUMNS.items():
            rows = connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()

            actual_columns = [row[1] for row in rows]

            assert actual_columns == expected_columns, (
                f"Unexpected columns for {table_name}: "
                f"{actual_columns}"
            )
    finally:
        connection.close()


def test_database_initialization_is_idempotent(tmp_path):
    """Calling initialization twice should not raise an error."""

    database_path = tmp_path / "test.db"

    init_database(database_path)
    init_database(database_path)

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        }

        assert tables == set(EXPECTED_COLUMNS)
    finally:
        connection.close()


def test_busy_timeout_is_5000_milliseconds(tmp_path):
    """Database connections should configure the expected busy timeout."""

    database_path = tmp_path / "test.db"
    init_database(database_path)

    connection = get_connection(database_path)
    try:
        timeout = connection.execute(
            "PRAGMA busy_timeout"
        ).fetchone()[0]

        assert timeout == 5000
    finally:
        connection.close()
