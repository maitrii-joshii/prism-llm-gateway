"""Application service for request logging and observability."""

import time
from typing import Any

from prism.config.logging import get_logger
from prism.domain.models import LogEntry, RequestContext
from prism.domain.security import hash_api_key
from prism.services.metrics import metrics_registry


logger = get_logger(__name__)


class RequestLoggingService:
    """Persist request metadata and record request metrics."""

    def save(
        self,
        context: RequestContext,
        log_repository: Any,
        status_code: int,
        request_started_at: float,
        raw_api_key: str | None = None,
    ) -> None:
        """Save a request log and update observability metrics."""

        if log_repository is None:
            logger.warning(
                "Request log repository is not configured",
                extra={"request_id": context.request_id},
            )
            return

        try:
            key_hash = (
                context.key_config.key_hash
                if context.key_config is not None
                else None
            )

            if key_hash is None and raw_api_key and raw_api_key.strip():
                key_hash = hash_api_key(raw_api_key)

            provider_response = context.provider_response

            latency_ms = max(
                0,
                int((time.perf_counter() - request_started_at) * 1000),
            )

            log_entry = LogEntry(
                request_id=context.request_id,
                key_hash=key_hash,
                model_requested=context.model_requested,
                model_resolved=context.model_resolved,
                provider=context.provider_name,
                status_code=status_code,
                prompt_tokens=(
                    provider_response.prompt_tokens
                    if provider_response is not None
                    else context.stream_prompt_tokens
                ),
                completion_tokens=(
                    provider_response.completion_tokens
                    if provider_response is not None
                    else context.stream_completion_tokens
                ),
                cost_usd=context.cost_usd,
                cache_result=context.cache_status,
                fallback_used=context.fallback_used,
                retries=context.retry_count,
                latency_ms=latency_ms,
                decision_trace=list(context.decision_trace),
            )

            log_repository.save_log(log_entry)

            self._record_metrics(
                context=context,
                log_entry=log_entry,
                status_code=status_code,
                latency_ms=latency_ms,
            )

            logger.info(
                "Request log saved",
                extra={
                    "request_id": context.request_id,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                },
            )

        except Exception:
            logger.exception(
                "Failed to save request log",
                extra={"request_id": context.request_id},
            )

    @staticmethod
    def _record_metrics(
        context: RequestContext,
        log_entry: LogEntry,
        status_code: int,
        latency_ms: int,
    ) -> None:
        """Record request, token, cost, and fallback metrics."""

        model_lbl = (
            context.model_resolved
            or context.model_requested
            or "unknown"
        )
        provider_lbl = context.provider_name or "none"
        cache_lbl = context.cache_status or "none"
        fallback_lbl = str(context.fallback_used).lower()

        metrics_registry.increment_counter(
            "prism_requests_total",
            1.0,
            {
                "model": model_lbl,
                "provider": provider_lbl,
                "status_code": str(status_code),
                "cache": cache_lbl,
                "fallback": fallback_lbl,
            },
        )

        metrics_registry.observe_duration(
            "prism_request_duration_seconds",
            latency_ms / 1000.0,
        )

        if log_entry.prompt_tokens:
            metrics_registry.increment_counter(
                "prism_tokens_total",
                float(log_entry.prompt_tokens),
                {"type": "prompt"},
            )

        if log_entry.completion_tokens:
            metrics_registry.increment_counter(
                "prism_tokens_total",
                float(log_entry.completion_tokens),
                {"type": "completion"},
            )

        if context.cost_usd > 0:
            metrics_registry.increment_counter(
                "prism_cost_usd_total",
                float(context.cost_usd),
                {
                    "tenant": (
                        context.key_config.tenant_id
                        if context.key_config
                        else "unknown"
                    )
                },
            )

        if context.fallback_used:
            metrics_registry.increment_counter(
                "prism_fallback_events_total",
                1.0,
                {
                    "model": model_lbl,
                    "provider": provider_lbl,
                },
            )


__all__ = ["RequestLoggingService"]
