"""Pipeline stage for semantic cache lookup."""

from prism.domain.models import RequestContext
from prism.services.cache import CacheService


def create_cache_stage(cache_service: CacheService):
    """Create an asynchronous cache lookup stage."""

    async def cache_stage(
        context: RequestContext,
    ) -> RequestContext:
        """Look up a cached response before provider execution.

        ``get_cached_response`` mutates *context* in-place (setting
        ``context.provider_response``, ``context.cache_status``, and
        ``context.cost_usd``) when it finds a hit, in addition to returning
        the ``ProviderResponse``.  We capture the return value here so the
        intent is explicit, even though the pipeline decision is driven by
        the context mutation.
        """

        cached = cache_service.get_cached_response(context)
        # If a cached response was found, context.provider_response is now set
        # and the pipeline will skip the provider call stage.
        _ = cached  # acknowledged; primary effect is on context
        return context

    return cache_stage


__all__ = ["create_cache_stage"]
