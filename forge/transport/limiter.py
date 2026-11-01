"""forge.transport.limiter - Rate limiting, circuit breakers, and concurrency controls."""
from __future__ import annotations

import asyncio
import random
import time
from typing import Optional


class TokenBucketLimiter:
    """Proactive token bucket rate limiter with randomized jitter."""

    def __init__(self, rate: float = 2.0, capacity: float = 5.0, jitter_pct: float = 0.2):
        self.rate = rate
        self.capacity = capacity
        self.jitter_pct = jitter_pct
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens < 1.0:
                deficit = 1.0 - self.tokens
                wait_time = deficit / self.rate
                jitter = wait_time * random.uniform(-self.jitter_pct, self.jitter_pct)
                sleep_duration = max(0.01, wait_time + jitter)
                await asyncio.sleep(sleep_duration)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class CircuitBreaker:
    """Reactive circuit breaker with exponential backoff on consecutive failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    async def record_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.opened_at = time.monotonic()

    async def record_success(self) -> None:
        async with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
            self.opened_at = None

    async def wait_if_tripped(self) -> None:
        while True:
            async with self._lock:
                if self.state == "CLOSED":
                    return
                now = time.monotonic()
                if self.opened_at and (now - self.opened_at >= self.recovery_timeout):
                    self.state = "HALF_OPEN"
                    return
                sleep_time = 2.0
            await asyncio.sleep(sleep_time)


class ConcurrencyController:
    """Manages worker concurrency and file descriptor safety limits."""

    def __init__(self, max_workers: int = 50):
        self.semaphore = asyncio.Semaphore(max_workers)
        self.active_workers = 0

    async def run_task(self, coro):
        async with self.semaphore:
            self.active_workers += 1
            try:
                return await coro
            finally:
                self.active_workers -= 1
