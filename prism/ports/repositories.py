from abc import ABC, abstractmethod
from typing import Any

from prism.domain.models import UsageRecord, VirtualKeyConfig


class KeyRepository(ABC):
    """Contract for retrieving and seeding virtual API keys."""

    @abstractmethod
    def get_by_hash(self, key_hash: str) -> VirtualKeyConfig | None:
        """Return a virtual key by its hash, or None if not found."""
        ...

    @abstractmethod
    def seed_keys(self, keys_list: list[VirtualKeyConfig]) -> None:
        """Seed the repository with virtual key configurations."""
        ...


class UsageRepository(ABC):
    """Contract for recording and retrieving usage."""

    @abstractmethod
    def record_usage(
        self,
        key_hash: str,
        month: str,
        cost: float,
        tokens: int,
        is_cache_hit: bool,
    ) -> None:
        """Record usage for a key and month."""
        ...

    @abstractmethod
    def get_usage(self, key_hash: str, month: str) -> UsageRecord:
        """Return usage for a key and month."""
        ...

    @abstractmethod
    def get_all_usage(self, month: str) -> list[UsageRecord]:
        """Return usage records for all keys in a month."""
        ...


class LogRepository(ABC):
    """Contract for saving and querying request logs."""

    @abstractmethod
    def save_log(self, log_entry: Any) -> None:
        """Save a request log entry."""
        ...

    @abstractmethod
    def get_logs(
        self,
        limit: int,
        offset: int,
        key_hash: str | None = None,
    ) -> list[Any]:
        """Return request logs, optionally filtered by key hash."""
        ...

    @abstractmethod
    def get_log(self, request_id: str) -> Any | None:
        """Return one request log, or None if it does not exist."""
        ...


class CacheRepository(ABC):
    """Contract for tenant-scoped semantic cache storage and lookup."""

    @abstractmethod
    def store(
        self,
        key_hash: str,
        alias: str,
        embedding: list[float],
        response_body: dict[str, Any],
    ) -> None:
        """Store a cached response and its embedding."""
        ...

    @abstractmethod
    def search(
        self,
        key_hash: str,
        alias: str,
        embedding: list[float],
        threshold: float,
    ) -> Any | None:
        """Find a sufficiently similar cached response for this key and alias."""
        ...

    @abstractmethod
    def get_stats(self, key_hash: str | None = None) -> Any:
        """Return cache statistics, optionally scoped to a key."""
        ...
