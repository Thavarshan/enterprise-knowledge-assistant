"""Enforce a process-local per-user token bucket.

Each synchronous consume call refills from a monotonic clock and deducts the
requested cost. Rejections report an approximate `Retry-After`. State is
neither locked for multithreaded access nor shared across workers, so the
limiter is suitable for the single-process demo topology only.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass


class RateLimitExceeded(PermissionError):
    """Signal that a user's token bucket cannot pay a request cost.

    Attributes:
        retry_after_seconds: Approximate time until the requested cost is
            available at the configured refill rate.
    """

    def __init__(self, retry_after_seconds: float) -> None:
        """Store the retry estimate with a generic rejection message.

        Args:
            retry_after_seconds: Seconds until the bucket can accept a
                request of the attempted cost.
        """
        super().__init__("Request rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _Bucket:
    """Track remaining capacity and the last refill timestamp.

    Attributes:
        tokens: Current fractional token balance.
        updated_at: Monotonic time at the last balance update.
    """

    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Apply a process-local token bucket per user.

    Each user starts with full capacity. A consume call replenishes tokens
    by elapsed monotonic time, caps at capacity, then deducts the cost.
    State is neither distributed nor protected by a lock, so deployments
    with multiple workers do not enforce one global quota.

    Attributes:
        capacity: Maximum tokens held by each bucket.
        refill_per_second: Refill speed applied independently per user.

    Concurrency:
        The mutable bucket map is not synchronized for threaded callers.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Validate limits and retain the clock used for refill calculations.

        Args:
            capacity: Maximum tokens per user; must be positive.
            refill_per_second: Positive refill rate.
            clock: Monotonic-time provider, injectable for deterministic
                tests.

        Raises:
            ValueError: A capacity or refill rate is not positive.
        """
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def consume(self, user_id: str, cost: float = 1) -> None:
        """Refill and charge one user's bucket atomically within this process.

        The bucket balance is capped at capacity so idle time cannot accrue
        an unbounded burst. A rejected cost leaves the computed balance
        available for a later retry.

        Args:
            user_id: Authenticated principal whose bucket is charged.
            cost: Positive token amount no greater than capacity.

        Raises:
            ValueError: Cost is outside the supported range.
            RateLimitExceeded: The refilled balance is insufficient.

        Notes:
            There is no thread lock or cross-process backing store.
        """
        if cost <= 0 or cost > self.capacity:
            raise ValueError(
                "cost must be positive and no greater than bucket capacity"
            )
        now = self._clock()
        bucket = self._buckets.get(user_id, _Bucket(self.capacity, now))
        # Monotonic elapsed time prevents clock adjustments; the cap limits
        # idle accumulation to one full burst.
        bucket.tokens = min(
            self.capacity,
            bucket.tokens
            + max(0.0, now - bucket.updated_at) * self.refill_per_second,
        )
        bucket.updated_at = now
        self._buckets[user_id] = bucket
        if bucket.tokens < cost:
            raise RateLimitExceeded(
                (cost - bucket.tokens) / self.refill_per_second
            )
        bucket.tokens -= cost
