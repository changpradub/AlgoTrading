"""
Market Data Client Module
Fetches historical bars and real-time quotes via Alpaca Historical Data Client.
Ensures rate-limited, async execution and returns clean pandas DataFrames for TA.
See UNIFIED_PLAN.md Section 4.1 & 4.2.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd
import structlog
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config.constants import WARMUP_BARS_MIN
from config.settings import settings
from utils.rate_limiter import alpaca_rest_limiter, BackoffHandler
from utils.timezone import now_utc, to_utc

logger = structlog.get_logger(__name__)


class MarketDataClient:
    """Async Market Data Client for US Stocks."""

    def __init__(self):
        self._backoff = BackoffHandler(base_delay=1.0, max_retries=3)
        self._client: Optional[StockHistoricalDataClient] = None

    def _ensure_client(self) -> StockHistoricalDataClient:
        """Instantiate market data client lazily."""
        if self._client is None:
            if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
                raise ValueError("Alpaca credentials are required for market data.")
            self._client = StockHistoricalDataClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
            )
        return self._client

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.Hour,
        limit: int = WARMUP_BARS_MIN,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars as a pandas DataFrame.
        Guarantees minimum bar count required for Indicator Warmup.
        """
        client = self._ensure_client()
        if end is None:
            end = now_utc()
        if start is None:
            # Look back sufficiently far to guarantee minimum bars
            start = end - timedelta(days=max(limit * 3, 30))

        request = StockBarsRequest(
            symbol_or_symbols=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
            feed=settings.ALPACA_DATA_FEED,
        )

        async with alpaca_rest_limiter:
            bar_set = await self._backoff.execute_with_retry(
                asyncio.to_thread, lambda: client.get_stock_bars(request)
            )

        data = bar_set.data.get(symbol.upper(), [])
        if not data:
            logger.warning("No historical bars returned", symbol=symbol)
            return pd.DataFrame()

        rows = []
        for bar in data:
            rows.append({
                "timestamp": to_utc(bar.timestamp),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
                "trade_count": getattr(bar, "trade_count", 0),
                "vwap": getattr(bar, "vwap", float(bar.close)),
            })

        df = pd.DataFrame(rows)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df

    async def get_latest_quote(self, symbol: str) -> Dict[str, float]:
        """Fetch latest bid and ask price for a symbol."""
        client = self._ensure_client()
        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbol.upper(),
            feed=settings.ALPACA_DATA_FEED,
        )

        async with alpaca_rest_limiter:
            quote_map = await self._backoff.execute_with_retry(
                asyncio.to_thread, lambda: client.get_stock_latest_quote(request)
            )

        quote = quote_map.get(symbol.upper())
        if not quote:
            raise ValueError(f"No quote available for {symbol}")

        return {
            "symbol": symbol.upper(),
            "bid_price": float(quote.bid_price),
            "ask_price": float(quote.ask_price),
            "bid_size": float(quote.bid_size),
            "ask_size": float(quote.ask_size),
            "timestamp": to_utc(quote.timestamp),
        }

    async def get_latest_bar(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest trade bar for a symbol."""
        client = self._ensure_client()
        request = StockLatestBarRequest(
            symbol_or_symbols=symbol.upper(),
            feed=settings.ALPACA_DATA_FEED,
        )

        async with alpaca_rest_limiter:
            bar_map = await self._backoff.execute_with_retry(
                asyncio.to_thread, lambda: client.get_stock_latest_bar(request)
            )

        bar = bar_map.get(symbol.upper())
        if not bar:
            raise ValueError(f"No latest bar for {symbol}")

        return {
            "symbol": symbol.upper(),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
            "timestamp": to_utc(bar.timestamp),
        }


# Global Market Data Client singleton
market_data_client = MarketDataClient()
