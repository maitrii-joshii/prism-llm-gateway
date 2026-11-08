"""SQLite database initialization and repository implementations for Prism."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Union, Any

from prism.adapters.bow_embedder import cosine_similarity
from prism.domain.models import (
    CacheEntry,
    CacheStats,
    LogEntry,
    MonthlyUsage,
    VirtualKeyConfig,
)
from prism.domain.security import hash_api_key
from prism.ports.repositories import (
    KeyRepository,
    LogRepository,
    UsageRepository,
)


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


class SQLiteKeyRepository(KeyRepository):
    """SQLite implementation of the virtual key repository."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def get_by_hash(
        self,
        key_hash: str,
    ) -> VirtualKeyConfig | None:
        """Find a virtual key by its SHA-256 hash."""

        connection = get_connection(self.database_path)

        try:
            row = connection.execute(
                """
                SELECT
                    key_hash,
                    tenant_id,
                    budget_usd,
                    rate_limit_rpm,
                    allowlist,
                    cache_enabled,
                    cache_threshold,
                    status
                FROM virtual_keys
                WHERE key_hash = ?
                """,
                (key_hash,),
            ).fetchone()

            if row is None:
                return None

            return VirtualKeyConfig(
                key_hash=row[0],
                tenant_id=row[1],
                budget_usd=row[2],
                rate_limit_rpm=row[3],
                model_allowlist=json.loads(row[4]),
                cache_enabled=bool(row[5]),
                cache_threshold=row[6],
                status=row[7],
            )

        finally:
            connection.close()

    def seed_keys(
        self,
        keys_list: list[VirtualKeyConfig],
    ) -> None:
        """Insert virtual key configurations without creating duplicates."""

        connection = get_connection(self.database_path)

        try:
            for key_config in keys_list:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO virtual_keys (
                        key_hash,
                        tenant_id,
                        budget_usd,
                        rate_limit_rpm,
                        allowlist,
                        cache_enabled,
                        cache_threshold,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key_config.key_hash,
                        key_config.tenant_id,
                        key_config.budget_usd,
                        key_config.rate_limit_rpm,
                        json.dumps(key_config.model_allowlist),
                        key_config.cache_enabled,
                        key_config.cache_threshold,
                        key_config.status,
                    ),
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()


class SQLiteUsageRepository(UsageRepository):
    """SQLite implementation of monthly usage tracking."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def record_usage(
        self,
        key_hash: str,
        month: str,
        cost: float,
        tokens: int,
        is_cache_hit: bool,
    ) -> None:
        """Atomically record usage for a key and calendar month."""

        if cost < 0:
            raise ValueError("cost cannot be negative.")

        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("tokens must be a non-negative integer.")

        if not isinstance(is_cache_hit, bool):
            raise ValueError("is_cache_hit must be a boolean.")

        connection = get_connection(self.database_path)

        try:
            connection.execute(
                """
                INSERT INTO usage (
                    key_hash,
                    month,
                    total_spend_usd,
                    total_tokens,
                    total_requests,
                    cache_hits
                )
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(key_hash, month)
                DO UPDATE SET
                    total_spend_usd =
                        total_spend_usd + excluded.total_spend_usd,
                    total_tokens =
                        total_tokens + excluded.total_tokens,
                    total_requests = total_requests + 1,
                    cache_hits = cache_hits + excluded.cache_hits
                """,
                (
                    key_hash,
                    month,
                    cost,
                    tokens,
                    int(is_cache_hit),
                ),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def get_usage(
        self,
        key_hash: str,
        month: str,
    ) -> MonthlyUsage:
        """Return monthly usage, or zero totals if no row exists."""

        connection = get_connection(self.database_path)

        try:
            row = connection.execute(
                """
                SELECT
                    key_hash,
                    month,
                    total_spend_usd,
                    total_tokens,
                    total_requests,
                    cache_hits
                FROM usage
                WHERE key_hash = ? AND month = ?
                """,
                (key_hash, month),
            ).fetchone()

            if row is None:
                return MonthlyUsage(
                    key_hash=key_hash,
                    month=month,
                    total_spend_usd=0.0,
                    total_tokens=0,
                    total_requests=0,
                    cache_hits=0,
                )

            return MonthlyUsage(
                key_hash=row[0],
                month=row[1],
                total_spend_usd=row[2],
                total_tokens=row[3],
                total_requests=row[4],
                cache_hits=row[5],
            )

        finally:
            connection.close()

    def get_all_usage(self, month: str) -> list[MonthlyUsage]:
        """Return monthly usage for every key with recorded usage."""

        connection = get_connection(self.database_path)

        try:
            rows = connection.execute(
                """
                SELECT
                    key_hash,
                    month,
                    total_spend_usd,
                    total_tokens,
                    total_requests,
                    cache_hits
                FROM usage
                WHERE month = ?
                ORDER BY key_hash
                """,
                (month,),
            ).fetchall()

            return [
                MonthlyUsage(
                    key_hash=row[0],
                    month=row[1],
                    total_spend_usd=row[2],
                    total_tokens=row[3],
                    total_requests=row[4],
                    cache_hits=row[5],
                )
                for row in rows
            ]

        finally:
            connection.close()


class SQLiteLogRepository(LogRepository):
    """SQLite implementation of request logging and retrieval."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def save_log(self, log_entry: LogEntry) -> None:
        """Save a request log entry."""

        if not isinstance(log_entry, LogEntry):
            raise TypeError("log_entry must be a LogEntry instance.")

        connection = get_connection(self.database_path)

        try:
            connection.execute(
                """
                INSERT INTO request_logs (
                    request_id,
                    key_hash,
                    model_requested,
                    model_resolved,
                    provider,
                    status_code,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    cache_result,
                    fallback_used,
                    retries,
                    latency_ms,
                    decision_trace,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_entry.request_id,
                    log_entry.key_hash,
                    log_entry.model_requested,
                    log_entry.model_resolved,
                    log_entry.provider,
                    log_entry.status_code,
                    log_entry.prompt_tokens,
                    log_entry.completion_tokens,
                    log_entry.cost_usd,
                    log_entry.cache_result,
                    int(log_entry.fallback_used),
                    log_entry.retries,
                    log_entry.latency_ms,
                    json.dumps(log_entry.decision_trace),
                    log_entry.created_at.isoformat(),
                ),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def get_logs(
        self,
        limit: int,
        offset: int,
        key_hash: str | None = None,
    ) -> list[LogEntry]:
        """Return request logs with pagination and optional key filtering."""

        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer.")

        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer.")

        connection = get_connection(self.database_path)

        try:
            query = """
                SELECT
                    request_id,
                    key_hash,
                    model_requested,
                    model_resolved,
                    provider,
                    status_code,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    cache_result,
                    fallback_used,
                    retries,
                    latency_ms,
                    decision_trace,
                    created_at
                FROM request_logs
            """

            parameters: tuple = ()

            if key_hash is not None:
                query += " WHERE key_hash = ?"
                parameters = (key_hash,)

            query += """
                ORDER BY created_at DESC, request_id DESC
                LIMIT ? OFFSET ?
            """

            parameters += (limit, offset)

            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

            return [
                self._row_to_log_entry(row)
                for row in rows
            ]

        finally:
            connection.close()

    def get_log(self, request_id: str) -> LogEntry | None:
        """Return one request log by request ID."""

        connection = get_connection(self.database_path)

        try:
            row = connection.execute(
                """
                SELECT
                    request_id,
                    key_hash,
                    model_requested,
                    model_resolved,
                    provider,
                    status_code,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    cache_result,
                    fallback_used,
                    retries,
                    latency_ms,
                    decision_trace,
                    created_at
                FROM request_logs
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()

            if row is None:
                return None

            return self._row_to_log_entry(row)

        finally:
            connection.close()

    @staticmethod
    def _row_to_log_entry(row: tuple) -> LogEntry:
        """Convert a SQLite request log row into a LogEntry model."""

        return LogEntry(
            request_id=row[0],
            key_hash=row[1],
            model_requested=row[2] or "",
            model_resolved=row[3],
            provider=row[4],
            status_code=row[5],
            prompt_tokens=row[6] or 0,
            completion_tokens=row[7] or 0,
            cost_usd=row[8] or 0.0,
            cache_result=row[9],
            fallback_used=bool(row[10]),
            retries=row[11] or 0,
            latency_ms=row[12],
            decision_trace=json.loads(row[13]) if row[13] else [],
            created_at=(
                datetime.fromisoformat(row[14])
                if row[14]
                else datetime.now(timezone.utc)
            ),
        )


class CacheRepository:
    """SQLite repository for tenant-isolated semantic cache entries."""

    def __init__(self, database_path: DatabasePath) -> None:
        self.database_path = database_path

    def store(
        self,
        key_hash: str,
        alias: str,
        embedding: list[float],
        response_body: dict[str, Any],
    ) -> None:
        """Store a cache entry with its embedding and response as JSON."""

        if not key_hash:
            raise ValueError("key_hash must not be empty.")

        if not alias:
            raise ValueError("alias must not be empty.")

        if not isinstance(embedding, list) or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in embedding
        ):
            raise ValueError("embedding must be a list of numbers.")

        if not isinstance(response_body, dict):
            raise ValueError("response_body must be a dictionary.")

        embedding_json = json.dumps(
            [float(value) for value in embedding]
        )
        response_json = json.dumps(response_body)

        prompt_hash = hashlib.sha256(
            embedding_json.encode("utf-8")
        ).hexdigest()

        connection = get_connection(self.database_path)

        try:
            connection.execute(
                """
                INSERT INTO cache_entries (
                    key_hash,
                    alias,
                    prompt_hash,
                    embedding,
                    response_body
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    alias,
                    prompt_hash,
                    embedding_json,
                    response_json,
                ),
            )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def search(
        self,
        key_hash: str,
        alias: str,
        embedding: list[float],
        threshold: float,
    ) -> CacheEntry | None:
        """
        Search only the authenticated key's cache entries.

        Tenant isolation is enforced directly in SQL before
        candidate embeddings are fetched.
        """

        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1.")

        if not isinstance(embedding, list) or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in embedding
        ):
            raise ValueError("embedding must be a list of numbers.")

        connection = get_connection(self.database_path)

        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    key_hash,
                    alias,
                    embedding,
                    response_body,
                    hit_count,
                    created_at
                FROM cache_entries
                WHERE key_hash = ? AND alias = ?
                ORDER BY created_at DESC, id DESC
                """,
                (key_hash, alias),
            ).fetchall()

            best_entry = None
            best_similarity = -1.0

            for row in rows:
                stored_embedding = json.loads(row[3])

                similarity = cosine_similarity(
                    [float(value) for value in embedding],
                    [float(value) for value in stored_embedding],
                )

                if similarity >= threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_entry = row

            if best_entry is None:
                return None

            connection.execute(
                """
                UPDATE cache_entries
                SET hit_count = hit_count + 1
                WHERE id = ? AND key_hash = ?
                """,
                (best_entry[0], key_hash),
            )

            connection.commit()

            return CacheEntry(
                id=best_entry[0],
                key_hash=best_entry[1],
                alias=best_entry[2],
                embedding=json.loads(best_entry[3]),
                response_body=json.loads(best_entry[4]),
                hit_count=best_entry[5] + 1,
                created_at=(
                    datetime.fromisoformat(best_entry[6])
                    if best_entry[6]
                    else datetime.now(timezone.utc)
                ),
            )

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def get_stats(
        self,
        key_hash: str | None = None,
    ) -> CacheStats:
        """Return cache statistics, optionally scoped to one key."""

        connection = get_connection(self.database_path)

        try:
            if key_hash is None:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*),
                        COALESCE(SUM(hit_count), 0)
                    FROM cache_entries
                    """
                ).fetchone()

            else:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*),
                        COALESCE(SUM(hit_count), 0)
                    FROM cache_entries
                    WHERE key_hash = ?
                    """,
                    (key_hash,),
                ).fetchone()

            return CacheStats(
                total_entries=row[0],
                total_hits=row[1],
            )

        finally:
            connection.close()


__all__ = [
    "create_tables",
    "get_connection",
    "init_database",
    "SQLiteKeyRepository",
    "SQLiteUsageRepository",
    "SQLiteLogRepository",
    "CacheRepository",
]
