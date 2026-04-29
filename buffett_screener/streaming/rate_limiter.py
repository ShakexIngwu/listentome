"""
streaming/rate_limiter.py
Async token bucket rate limiter.
Prevents IP bans from Yahoo Finance and SEC EDGAR by capping request throughput.
"""
import asyncio
import time


class TokenBucket:
    """
    Thread-safe async token bucket.
    Allows `rate` calls per second, with a burst capacity of `capacity`.
    Call `await bucket.acquire()` before each outbound request.
    """

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = rate
        self.capacity = capacity or rate * 2
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1
