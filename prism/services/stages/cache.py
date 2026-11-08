"""Pipeline stage for semantic cache lookup."""

from prism.domain.models import RequestContext
from prism.services.cache import CacheService


def create_cache_stage(cache_service: CacheService):
    """Create an asynchronous cache lookup stage."""

    async def cache_stage(
        context: RequestContext,
    ) -> RequestContext:
        """Look up a cached response before provider execution."""

        cache_service.get_cached_response(context)
        return context

    return cache_stage


__all__ = ["create_cache_stage"]
