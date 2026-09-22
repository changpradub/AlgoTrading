"""
Async Rate Limiter Module
Implements a token bucket algorithm to enforce Alpaca's 200 requests/minute limit,
with exponential backoff and jitter for resilient error recovery.
See UNIFIED_PLAN.md Section 4.1.
"""

import asyncio
import random
import time
from typing import Optional
import structlog

from config.constants import (
    ALPACA_REST_MAX_REQ_PER_MINUTE,
    ALPACA_REST_SAFETY_REQ_PER_MINUTE,
)

logger = structlog.get_logger(__name__)


class AsyncRateLimiter:
    """
    Token Bucket Rate Limiter for asyncio.
    Enforces a strict ceiling on requests per minute with safety margin.
    """

    def __init__(
        self,
        max_rate: int = ALPACA_REST_SAFETY_REQ_PER_MINUTE,
        time_period: float = 60.0,
    ):
        self.max_rate = max_rate
        self.time_period = time_period
        self.tokens = float(max_rate)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Wait until enough tokens are available, then consume them."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Replenish tokens based on elapsed time
                self.tokens = min(
                    float(self.max_rate),
                    self.tokens + elapsed * (self.max_rate / self.time_period),
                )

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate sleep duration needed for required tokens
                missing_tokens = tokens - self.tokens
                wait_time = missing_tokens * (self.time_period / self.max_rate)

            # Sleep outside the lock to allow other coroutines to check
            await asyncio.sleep(max(wait_time, 0.05))

    async def __aenter__(self):
        await self.acquire(1.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class BackoffHandler:
    """
    Exponential Backoff with Jitter for HTTP 429 and transient network failures.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        factor: float = 2.0,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.factor = factor

    async def execute_with_retry(self, coro_func, *args, **kwargs):
        """
        Execute an async callable with exponential backoff on failure.
        """
        attempt = 0
        while True:
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                attempt += 1
                if attempt > self.max_retries:
                    logger.error(
                        "Max retries exceeded",
                        attempt=attempt,
                        error=str(e),
                    )
                    raise

                # Calculate exponential delay with randomized jitter
                calculated_delay = self.base_delay * (self.factor ** (attempt - 1))
                jitter = random.uniform(0.1, 0.5) * calculated_delay
                delay = min(self.max_delay, calculated_delay + jitter)

                logger.warning(
                    "Retrying failed async request",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    delay_seconds=round(delay, 2),
                    error=str(e),
                )
                await asyncio.sleep(delay)


# Default global rate limiter for Alpaca REST API
alpaca_rest_limiter = AsyncRateLimiter(max_rate=ALPACA_REST_SAFETY_REQ_PER_MINUTE)
