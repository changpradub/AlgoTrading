"""
Market Hours Scheduler Module
Manages US stock market hours (Regular Hours: 09:30-16:00 ET), Pre-market window,
and market holidays using Alpaca's get_clock() and get_calendar() APIs.
Ensures the bot stays idle during market closure and wakes up on schedule.
See UNIFIED_PLAN.md Section 4.0.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from utils.timezone import (
    now_utc,
    to_utc,
    to_eastern,
    to_bangkok,
    format_multi_tz_display,
)

logger = structlog.get_logger(__name__)


class MarketPhase(str, Enum):
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    REGULAR_HOURS = "regular_hours"
    AFTER_HOURS = "after_hours"


@dataclass
class MarketClockSnapshot:
    is_open: bool
    phase: MarketPhase
    timestamp_utc: datetime
    next_open_utc: datetime
    next_close_utc: datetime
    time_to_open_seconds: float
    time_to_close_seconds: float

    @property
    def is_regular_hours(self) -> bool:
        return self.phase == MarketPhase.REGULAR_HOURS


class MarketHoursScheduler:
    """
    Coordinates bot activity based on official Alpaca market clock.
    Controls idle states, warmup triggers, and pre-market scanning windows.
    """

    def __init__(self, pre_market_scan_minutes: int = 30):
        self.pre_market_scan_minutes = pre_market_scan_minutes
        self._cached_snapshot: Optional[MarketClockSnapshot] = None
        self._last_checked_utc: Optional[datetime] = None

    async def get_market_status(self, force_refresh: bool = False) -> MarketClockSnapshot:
        """
        Fetch and parse Alpaca market clock.
        Caches for 30 seconds unless force_refresh is True.
        """
        now = now_utc()
        if (
            not force_refresh
            and self._cached_snapshot is not None
            and self._last_checked_utc is not None
            and (now - self._last_checked_utc).total_seconds() < 30
        ):
            return self._cached_snapshot

        try:
            clock = await alpaca_trading_client.get_clock()
            ts_utc = to_utc(clock.timestamp)
            next_open_utc = to_utc(clock.next_open)
            next_close_utc = to_utc(clock.next_close)

            # Determine market phase
            if clock.is_open:
                phase = MarketPhase.REGULAR_HOURS
            else:
                # Check if we are in the pre-market window before next_open
                time_to_open = (next_open_utc - ts_utc).total_seconds()
                if 0 <= time_to_open <= (self.pre_market_scan_minutes * 60):
                    phase = MarketPhase.PRE_MARKET
                else:
                    phase = MarketPhase.CLOSED

            time_to_open_sec = max(0.0, (next_open_utc - ts_utc).total_seconds())
            time_to_close_sec = max(0.0, (next_close_utc - ts_utc).total_seconds())

            snapshot = MarketClockSnapshot(
                is_open=clock.is_open,
                phase=phase,
                timestamp_utc=ts_utc,
                next_open_utc=next_open_utc,
                next_close_utc=next_close_utc,
                time_to_open_seconds=time_to_open_sec,
                time_to_close_seconds=time_to_close_sec,
            )

            self._cached_snapshot = snapshot
            self._last_checked_utc = now
            return snapshot

        except Exception as e:
            logger.error("Failed to query Alpaca clock", error=str(e))
            # Fallback to local timezone calculation
            return self._compute_local_fallback()

    def _compute_local_fallback(self) -> MarketClockSnapshot:
        """Fallback local calculation when Alpaca API is unavailable."""
        now = now_utc()
        et = to_eastern(now)
        # Weekday 0-4 = Monday-Friday
        is_weekday = et.weekday() < 5
        market_open_today = et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close_today = et.replace(hour=16, minute=0, second=0, microsecond=0)

        is_open = is_weekday and (market_open_today <= et < market_close_today)
        phase = MarketPhase.REGULAR_HOURS if is_open else MarketPhase.CLOSED

        return MarketClockSnapshot(
            is_open=is_open,
            phase=phase,
            timestamp_utc=now,
            next_open_utc=to_utc(market_open_today),
            next_close_utc=to_utc(market_close_today),
            time_to_open_seconds=0.0,
            time_to_close_seconds=0.0,
        )

    async def wait_until_market_open(self, poll_interval_sec: int = 60) -> None:
        """
        Pause bot execution loop until regular market hours commence.
        """
        while True:
            status = await self.get_market_status(force_refresh=True)
            if status.is_regular_hours:
                logger.info(
                    "Regular market hours active. Commencing trading pipeline.",
                    time=format_multi_tz_display(status.timestamp_utc),
                )
                return

            hours_left = round(status.time_to_open_seconds / 3600, 2)
            logger.info(
                f"Market is {status.phase.value}. Waiting for market open.",
                hours_remaining=hours_left,
                next_open=format_multi_tz_display(status.next_open_utc),
            )

            sleep_duration = min(poll_interval_sec, max(10.0, status.time_to_open_seconds))
            await asyncio.sleep(sleep_duration)


# Global Scheduler singleton
market_scheduler = MarketHoursScheduler()
