"""Application service for semantic response caching."""

import json
from typing import Any

from prism.ports.embedder import Embedder
from prism.ports.repositories import CacheRepository
from prism.domain.cache_decision import (
    TIME_SENSITIVE_KEYWORDS,
    is_cacheable,
)
from prism.domain.models import ProviderResponse, RequestContext


class CacheService:
    """Coordinate embedding, cache lookup, and response storage."""

    def __init__(
        self,
        embedder: Embedder,
        repository: CacheRepository,
    ) -> None:
        self.embedder = embedder
        self.repository = repository

    @staticmethod
    def _get_prompt(context: RequestContext) -> str:
        """Extract message content into a deterministic prompt string."""

        return json.dumps(
            context.messages,
            sort_keys=True,
            ensure_ascii=False,
        )

    @staticmethod
    def _is_request_eligible(context: RequestContext) -> bool:
        """Check whether the request is eligible for cache lookup."""

        if context.key_config is None:
            return False

        if not context.key_config.cache_enabled:
            return False

        prompt = CacheService._get_prompt(context).lower()

        if any(
            keyword in prompt
            for keyword in TIME_SENSITIVE_KEYWORDS
        ):
            return False

        return True

    def get_cached_response(
        self,
        context: RequestContext,
    ) -> ProviderResponse | None:
        """Find a sufficiently similar cached response for this request."""

        context.cache_status = "miss"

        if not self._is_request_eligible(context):
            context.decision_trace.append(
                "semantic cache lookup skipped"
            )
            return None

        if context.key_config is None:
            return None

        alias = context.model_requested

        if not alias:
            return None

        prompt = self._get_prompt(context)
        embedding = self.embedder.embed(prompt)

        entry = self.repository.search(
            key_hash=context.key_config.key_hash,
            alias=alias,
            embedding=embedding,
            threshold=context.key_config.cache_threshold,
        )

        if entry is None:
            context.decision_trace.append(
                "semantic cache miss"
            )
            return None

        cached_response = ProviderResponse.model_validate(
            entry.response_body
        )

        context.provider_response = cached_response
        context.model_resolved = cached_response.model
        context.cache_status = "hit"
        context.cost_usd = 0.0

        context.decision_trace.append(
            f"semantic cache hit: similarity threshold "
            f"{context.key_config.cache_threshold}"
        )

        return cached_response

    def store_response(
        self,
        context: RequestContext,
    ) -> None:
        """Store a successful provider response in the semantic cache."""

        if not is_cacheable(context):
            context.decision_trace.append(
                "semantic cache storage skipped"
            )
            return

        if context.key_config is None:
            return

        if context.provider_response is None:
            return

        alias = context.model_requested

        if not alias:
            return

        prompt = self._get_prompt(context)
        embedding = self.embedder.embed(prompt)

        response_body: dict[str, Any] = (
            context.provider_response.model_dump(mode="json")
        )

        self.repository.store(
            key_hash=context.key_config.key_hash,
            alias=alias,
            embedding=embedding,
            response_body=response_body,
        )

        context.decision_trace.append(
            "successful provider response stored in semantic cache"
        )


__all__ = ["CacheService"]
