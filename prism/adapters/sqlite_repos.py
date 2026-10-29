"""SQLite database initialization and schema creation for Prism."""

import sqlite3
from pathlib import Path
from typing import Union


DatabasePath = Union[str, Path]

BUSY_TIMEOUT_MS = 5000


def create_tables(connection: sqlite3.Connection) -> None:
    """Create all Prism database tables if they do not already exist."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS virtual_keys (
            key_hash TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            budget_usd REAL NOT NULL,
            rate_limit_rpm INTEGER NOT NULL,
            allowlist TEXT NOT NULL,
            cache_enabled BOOLEAN DEFAULT 1,
            cache_threshold REAL DEFAULT 0.85,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS usage (
            key_hash TEXT NOT NULL,
            month TEXT NOT NULL,
            total_spend_usd REAL DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            cache_hits INTEGER DEFAULT 0,
            PRIMARY KEY (key_hash, month)
        );

        CREATE TABLE IF NOT EXISTS request_logs (
            request_id TEXT PRIMARY KEY,
            key_hash TEXT,
            model_requested TEXT,
            model_resolved TEXT,
            provider TEXT,
            status_code INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd REAL,
            cache_result TEXT,
            fallback_used BOOLEAN DEFAULT 0,
            retries INTEGER DEFAULT 0,
            latency_ms INTEGER,
            decision_trace TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cache_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL,
            alias TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            embedding TEXT NOT NULL,
            response_body TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def get_connection(database_path: DatabasePath) -> sqlite3.Connection:
    """Open a SQLite connection with a 5-second busy timeout."""

    connection = sqlite3.connect(
        str(database_path),
        timeout=BUSY_TIMEOUT_MS / 1000,
    )

    connection.execute(
        f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}"
    )

    return connection


def init_database(database_path: DatabasePath) -> None:
    """Initialize the database and create its tables if necessary."""

    # Create the parent directory for a file-based database if needed.
    if str(database_path) != ":memory:":
        Path(database_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    connection = get_connection(database_path)

    try:
        create_tables(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
