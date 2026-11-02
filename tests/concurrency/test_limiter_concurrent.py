"""Concurrency tests for the token bucket rate limiter."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from prism.domain.limiter import TokenBucketRateLimiter
from prism.ports.clock import Clock


class FakeClock(Clock):
    """Thread-safe test clock with a fixed timestamp."""

    def __init__(self):
        self.current_time = datetime(
            2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc
        )

    def now(self):
        return self.current_time


def test_concurrent_requests_do_not_over_admit_tokens():
    """
    Exactly 10 of 20 concurrent requests should be accepted.

    All requests use the same API key and share one token bucket.
    """

    clock = FakeClock()
    limiter = TokenBucketRateLimiter(clock)

    key_hash = "concurrent-test-key"
    rpm_limit = 10
    total_requests = 20

    def make_request(_):
        return limiter.try_acquire(
            key_hash=key_hash,
            rpm_limit=rpm_limit,
        )

    # Launch 20 requests using 20 worker threads.
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(make_request, range(total_requests))
        )

    allowed = sum(results)
    rejected = total_requests - allowed

    assert allowed == 10
    assert rejected == 10
    assert limiter.buckets[key_hash].tokens == 0
