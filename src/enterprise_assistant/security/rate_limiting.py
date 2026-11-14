"""Small process-local token bucket for development request protection."""

import time
from collections.abc import Callable
from dataclasses import dataclass


class RateLimitExceeded(PermissionError):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("Request rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Per-user token bucket; state is not shared between worker processes."""

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def consume(self, user_id: str, cost: float = 1) -> None:
        if cost <= 0 or cost > self.capacity:
            raise ValueError("cost must be positive and no greater than bucket capacity")
        now = self._clock()
        bucket = self._buckets.get(user_id, _Bucket(self.capacity, now))
        bucket.tokens = min(
            self.capacity,
            bucket.tokens + max(0.0, now - bucket.updated_at) * self.refill_per_second,
        )
        bucket.updated_at = now
        self._buckets[user_id] = bucket
        if bucket.tokens < cost:
            raise RateLimitExceeded((cost - bucket.tokens) / self.refill_per_second)
        bucket.tokens -= cost
