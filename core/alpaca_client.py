"""
Async Alpaca Trading Client Wrapper
Wraps Alpaca TradingClient with asyncio.to_thread and alpaca_rest_limiter
to ensure non-blocking, rate-limited REST execution.
See UNIFIED_PLAN.md Section 4.0 & Section 7.
"""

import asyncio
from datetime import date
from typing import Any, List, Optional
import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.models import TradeAccount, Clock, Calendar, Position, Order
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from config.settings import settings
from utils.rate_limiter import alpaca_rest_limiter, BackoffHandler

logger = structlog.get_logger(__name__)


class AlpacaAsyncTradingClient:
    """Non-blocking async wrapper around Alpaca TradingClient."""

    def __init__(self):
        self._backoff = BackoffHandler(base_delay=1.0, max_retries=3)
        self._client: Optional[TradingClient] = None
        self._initialized = False

    def _ensure_client(self) -> TradingClient:
        """Instantiate client lazily if not already created."""
        if self._client is None:
            if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
                raise ValueError("Alpaca API credentials are not set in environment.")
            self._client = TradingClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
                paper=settings.is_paper_trading,
            )
        return self._client

    async def get_account(self) -> TradeAccount:
        """Fetch account details (equity, buying power, daytrade count)."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            return await self._backoff.execute_with_retry(
                asyncio.to_thread, client.get_account
            )

    async def get_clock(self) -> Clock:
        """Fetch current market clock (is_open, next_open, next_close)."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            return await self._backoff.execute_with_retry(
                asyncio.to_thread, client.get_clock
            )

    async def get_calendar(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> List[Calendar]:
        """Fetch market calendar for holidays and trading days."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            return await self._backoff.execute_with_retry(
                asyncio.to_thread,
                lambda: client.get_calendar(start=start, end=end),
            )

    async def get_all_positions(self) -> List[Position]:
        """Fetch all open positions."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            return await self._backoff.execute_with_retry(
                asyncio.to_thread, client.get_all_positions
            )

    async def get_open_orders(self) -> List[Order]:
        """Fetch all open/pending orders."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            return await self._backoff.execute_with_retry(
                asyncio.to_thread, lambda: client.get_orders(filter=req)
            )

    async def cancel_order_by_id(self, order_id: str) -> None:
        """Cancel a specific order by ID."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            await self._backoff.execute_with_retry(
                asyncio.to_thread, lambda: client.cancel_order_by_id(order_id)
            )
            logger.info("Order canceled", order_id=order_id)

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders (safety switch action)."""
        async with alpaca_rest_limiter:
            client = self._ensure_client()
            await self._backoff.execute_with_retry(
                asyncio.to_thread, client.cancel_orders
            )
            logger.warning("All open orders canceled via emergency action")


# Singleton instance
alpaca_trading_client = AlpacaAsyncTradingClient()
