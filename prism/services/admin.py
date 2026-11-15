"""Admin service for gateway statistics and reporting."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from prism.domain.models import CacheStats


@dataclass(frozen=True)
class CacheStatistics:
    """Aggregated cache statistics for the admin API."""

    stats: CacheStats
    cache_hit_rate: float
    cache_hits_this_month: int
    total_requests_this_month: int


class AdminService:
    """Handle business logic for admin reporting."""

    def __init__(
        self,
        cache_repository: Any,
        usage_repository: Any,
    ) -> None:
        self.cache_repository = cache_repository
        self.usage_repository = usage_repository

    @classmethod
    def from_app_state(cls, state: Any) -> "AdminService":
        """Build the service using repositories initialized at startup."""

        return cls(
            cache_repository=state.cache_repository,
            usage_repository=state.usage_repository,
        )

    def get_cache_statistics(self) -> CacheStatistics:
        """Calculate aggregate cache statistics and monthly hit rate."""

        stats = self.cache_repository.get_stats()

        selected_month = datetime.now(
            timezone.utc
        ).strftime("%Y-%m")

        usage_records = self.usage_repository.get_all_usage(
            selected_month
        )

        total_requests = sum(
            record.total_requests for record in usage_records
        )

        total_cache_hits = sum(
            record.cache_hits for record in usage_records
        )

        cache_hit_rate = (
            total_cache_hits / total_requests
            if total_requests > 0
            else 0.0
        )

        return CacheStatistics(
            stats=stats,
            cache_hit_rate=round(cache_hit_rate, 4),
            cache_hits_this_month=total_cache_hits,
            total_requests_this_month=total_requests,
        )
