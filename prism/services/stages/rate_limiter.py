"""Rate limiting stage for the Prism request pipeline."""

from prism.domain.errors import AuthenticationError, RateLimitError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.domain.models import RequestContext


async def enforce_rate_limit(
    context: RequestContext,
    limiter: TokenBucketRateLimiter,
) -> RequestContext:
    """Enforce the authenticated virtual key's RPM limit."""

    # Authentication must happen before rate limiting.
    if context.key_config is None:
        raise AuthenticationError(
            "Request must be authenticated before rate limiting."
        )

    key_hash = context.key_config.key_hash
    rpm_limit = context.key_config.rate_limit_rpm

    allowed = limiter.try_acquire(
        key_hash=key_hash,
        rpm_limit=rpm_limit,
    )

    if not allowed:
        context.decision_trace.append("rate limited")
        raise RateLimitError(
            "Rate limit exceeded. Please try again later."
        )

    context.decision_trace.append("rate ok")

    return context
