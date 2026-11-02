"""Unit tests for the token bucket rate limiter."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from prism.domain.limiter import TokenBucketRateLimiter
from prism.ports.clock import Clock


class FakeClock(Clock):
    """Clock whose time can be advanced manually."""

    def __init__(self):
        self.current_time = datetime(
            2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc
        )

    def now(self):
        return self.current_time

    def advance(self, seconds: float):
        self.current_time += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return TokenBucketRateLimiter(clock)


def test_allows_exactly_rpm_limit_initial_requests(limiter):
    """Allows exactly N requests and rejects request N+1."""

    rpm_limit = 3

    for _ in range(rpm_limit):
        assert limiter.try_acquire("key-1", rpm_limit) is True

    assert limiter.try_acquire("key-1", rpm_limit) is False


def test_rejects_request_after_bucket_is_empty(limiter):
    """Rejects requests when no tokens are available."""

    for _ in range(3):
        limiter.try_acquire("key-1", 3)

    assert limiter.try_acquire("key-1", 3) is False


def test_refills_one_token_after_twenty_seconds(limiter, clock):
    """At 3 RPM, one token is refilled every 20 seconds."""

    for _ in range(3):
        limiter.try_acquire("key-1", 3)

    clock.advance(20)

    assert limiter.try_acquire("key-1", 3) is True
    assert limiter.try_acquire("key-1", 3) is False


def test_refills_tokens_over_time(limiter, clock):
    """Multiple tokens are refilled as time advances."""

    for _ in range(3):
        limiter.try_acquire("key-1", 3)

    clock.advance(40)

    assert limiter.try_acquire("key-1", 3) is True
    assert limiter.try_acquire("key-1", 3) is True
    assert limiter.try_acquire("key-1", 3) is False


def test_different_keys_have_independent_buckets(limiter):
    """Different API keys maintain independent token buckets."""

    for _ in range(3):
        limiter.try_acquire("key-1", 3)

    assert limiter.try_acquire("key-1", 3) is False

    # key-2 has its own full bucket.
    assert limiter.try_acquire("key-2", 3) is True


def test_bucket_never_exceeds_capacity(limiter, clock):
    """Refilled tokens never exceed the bucket capacity."""

    limiter.try_acquire("key-1", 3)

    clock.advance(120)

    assert limiter.try_acquire("key-1", 3) is True

    bucket = limiter.buckets["key-1"]
    assert bucket.tokens <= 3


def test_rejects_zero_or_negative_rpm(limiter):
    """Zero and negative RPM values raise ValueError."""

    with pytest.raises(ValueError):
        limiter.try_acquire("key-1", 0)

    with pytest.raises(ValueError):
        limiter.try_acquire("key-1", -1)


def test_one_rpm_allows_one_request_and_refills_after_sixty_seconds(
    limiter,
    clock,
):
    """At 1 RPM, one token is refilled every 60 seconds."""

    assert limiter.try_acquire("key-1", 1) is True
    assert limiter.try_acquire("key-1", 1) is False

    # 59 seconds is not enough to refill one token.
    clock.advance(59)

    assert limiter.try_acquire("key-1", 1) is False

    # At 60 seconds, one token becomes available.
    clock.advance(1)

    assert limiter.try_acquire("key-1", 1) is True
    assert limiter.try_acquire("key-1", 1) is False


def test_concurrent_requests_cannot_consume_same_token(limiter):
    """Concurrent requests cannot consume more tokens than available."""

    # Capacity is 10, so exactly 10 of 100 requests should succeed.
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                lambda _: limiter.try_acquire("key-1", 10),
                range(100),
            )
        )

    assert sum(results) == 10
