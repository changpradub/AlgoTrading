"""
Unit tests for core/scheduler.py
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch

from core.scheduler import MarketHoursScheduler, MarketPhase


@pytest.mark.asyncio
async def test_scheduler_fallback():
    scheduler = MarketHoursScheduler(pre_market_scan_minutes=30)
    fallback = scheduler._compute_local_fallback()
    assert fallback is not None
    assert fallback.phase in (MarketPhase.REGULAR_HOURS, MarketPhase.CLOSED)


@pytest.mark.asyncio
async def test_scheduler_with_mock_clock_open():
    scheduler = MarketHoursScheduler(pre_market_scan_minutes=30)

    class MockClock:
        is_open = True
        timestamp = datetime(2026, 9, 22, 14, 0, 0, tzinfo=timezone.utc)
        next_open = datetime(2026, 9, 23, 13, 30, 0, tzinfo=timezone.utc)
        next_close = datetime(2026, 9, 22, 20, 0, 0, tzinfo=timezone.utc)

    with patch("core.scheduler.alpaca_trading_client.get_clock", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockClock()
        status = await scheduler.get_market_status(force_refresh=True)

        assert status.is_open is True
        assert status.phase == MarketPhase.REGULAR_HOURS
        assert status.is_regular_hours is True


@pytest.mark.asyncio
async def test_scheduler_with_mock_clock_pre_market():
    scheduler = MarketHoursScheduler(pre_market_scan_minutes=45)

    class MockClock:
        is_open = False
        # 20 minutes before next open
        timestamp = datetime(2026, 9, 22, 13, 10, 0, tzinfo=timezone.utc)
        next_open = datetime(2026, 9, 22, 13, 30, 0, tzinfo=timezone.utc)
        next_close = datetime(2026, 9, 22, 20, 0, 0, tzinfo=timezone.utc)

    with patch("core.scheduler.alpaca_trading_client.get_clock", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockClock()
        status = await scheduler.get_market_status(force_refresh=True)

        assert status.is_open is False
        assert status.phase == MarketPhase.PRE_MARKET
        assert status.is_regular_hours is False
