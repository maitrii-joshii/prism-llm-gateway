"""Application service for recording completion usage."""

from typing import Any

from prism.domain.errors import UpstreamError
from prism.domain.models import RequestContext


class UsageRecordingService:
    """Record token and cost usage for completed requests."""

    def record(self, context: RequestContext, usage_repository: Any) -> None:
        """Persist usage for non-streaming requests and cache hits."""

        if context.provider_response is None:
            return

        if context.key_config is None:
            raise UpstreamError(
                "Authenticated key configuration is missing."
            )

        usage_repository.record_usage(
            key_hash=context.key_config.key_hash,
            month=context.start_time.strftime("%Y-%m"),
            cost=context.cost_usd,
            tokens=context.provider_response.total_tokens,
            is_cache_hit=context.cache_status == "hit",
        )

        context.decision_trace.append(
            f"usage recorded: {context.provider_response.total_tokens} tokens"
        )


__all__ = ["UsageRecordingService"]
