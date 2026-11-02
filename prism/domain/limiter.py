"""In-memory token bucket rate limiter for Prism."""

import threading
from dataclasses import dataclass
from datetime import datetime

from prism.ports.clock import Clock


@dataclass
class TokenBucket:
    """Track token count and last refill time for one API key."""

    tokens: float
    last_refill_at: datetime


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def try_acquire(self, key_hash: str, rpm_limit: int) -> bool:
        """Consume one token if available; otherwise reject."""

        if rpm_limit <= 0:
            raise ValueError("rpm_limit must be greater than zero")

        with self.lock:
            now = self.clock.now()

            bucket = self.buckets.get(key_hash)

            # Create a full bucket for a new API key.
            if bucket is None:
                bucket = TokenBucket(
                    tokens=float(rpm_limit),
                    last_refill_at=now,
                )
                self.buckets[key_hash] = bucket

            else:
                elapsed_seconds = (
                    now - bucket.last_refill_at
                ).total_seconds()

                if elapsed_seconds > 0:
                    refill_rate = rpm_limit / 60.0
                    tokens_to_add = elapsed_seconds * refill_rate

                    bucket.tokens = min(
                        float(rpm_limit),
                        bucket.tokens + tokens_to_add,
                    )
                    bucket.last_refill_at = now

                # Enforce the current capacity.
                bucket.tokens = min(
                    bucket.tokens,
                    float(rpm_limit),
                )

            # Check and decrement happen under the same lock.
            if bucket.tokens < 1.0:
                return False

            bucket.tokens -= 1.0
            return True
