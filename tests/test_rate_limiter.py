"""
Unit tests for utils/rate_limiter.py
"""

import asyncio
import time
import pytest
from utils.rate_limiter import AsyncRateLimiter, BackoffHandler


@pytest.mark.asyncio
async def test_rate_limiter_immediate_acquire():
    limiter = AsyncRateLimiter(max_rate=10, time_period=1.0)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire(1.0)
    elapsed = time.monotonic() - start
    # 5 tokens within capacity of 10 should be instantaneous
    assert elapsed < 0.2


@pytest.mark.asyncio
async def test_rate_limiter_throttles_when_exhausted():
    limiter = AsyncRateLimiter(max_rate=3, time_period=0.5)
    # Drain initial 3 tokens
    await limiter.acquire(3.0)

    start = time.monotonic()
    # Now acquire 1 token, should wait for replenishment
    await limiter.acquire(1.0)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_backoff_retry_success():
    handler = BackoffHandler(base_delay=0.05, max_retries=3, factor=1.5)
    attempts = 0

    async def flaky_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionResetError("Transient network failure")
        return "success"

    result = await handler.execute_with_retry(flaky_operation)
    assert result == "success"
    assert attempts == 3


@pytest.mark.asyncio
async def test_backoff_max_retries_exceeded():
    handler = BackoffHandler(base_delay=0.01, max_retries=2, factor=1.5)

    async def permanent_failure():
        raise ValueError("Unrecoverable error")

    with pytest.raises(ValueError):
        await handler.execute_with_retry(permanent_failure)
