"""
News Fetcher Module
Fetches real-time financial market news for target symbols using Alpaca News API (Benzinga feed).
Supports async execution and caches articles.
See UNIFIED_PLAN.md Section 4.4.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import structlog
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from config.settings import settings
from db.connection import db_manager
from utils.timezone import now_utc, to_utc

logger = structlog.get_logger(__name__)


@dataclass
class NewsArticle:
    id: str
    headline: str
    summary: str
    symbols: List[str]
    published_at: datetime
    url: str
    source: str


class NewsFetcher:
    """Async news aggregator using Alpaca's news stream."""

    def __init__(self):
        self._client: Optional[NewsClient] = None

    def _ensure_client(self) -> NewsClient:
        if self._client is None:
            if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
                raise ValueError("Alpaca credentials are required for News API.")
            self._client = NewsClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
            )
        return self._client

    async def fetch_news_for_symbol(self, symbol: str, limit: int = 5) -> List[NewsArticle]:
        """
        Fetch recent news articles for a single stock symbol asynchronously.
        """
        client = self._ensure_client()
        request = NewsRequest(symbols=symbol.upper(), limit=limit, sort="desc")

        try:
            news_set = await asyncio.to_thread(client.get_news, request)
            raw_items = news_set.data.get("news", []) if hasattr(news_set, "data") else []

            articles: List[NewsArticle] = []
            for item in raw_items:
                if isinstance(item, dict):
                    art = NewsArticle(
                        id=str(item.get("id", "")),
                        headline=item.get("headline", ""),
                        summary=item.get("summary", ""),
                        symbols=[s.upper() for s in item.get("symbols", [])],
                        published_at=to_utc(item.get("created_at", now_utc())),
                        url=item.get("url", ""),
                        source=item.get("source", "benzinga"),
                    )
                else:
                    created = getattr(item, "created_at", now_utc())
                    art = NewsArticle(
                        id=str(getattr(item, "id", "")),
                        headline=getattr(item, "headline", ""),
                        summary=getattr(item, "summary", ""),
                        symbols=[s.upper() for s in getattr(item, "symbols", [])],
                        published_at=to_utc(created),
                        url=getattr(item, "url", ""),
                        source=getattr(item, "source", "benzinga"),
                    )
                articles.append(art)

            logger.info("News fetched successfully", symbol=symbol, count=len(articles))

            # Async cache into database if available
            await self._cache_articles(articles)
            return articles

        except Exception as e:
            logger.error("Failed to fetch news", symbol=symbol, error=str(e))
            return []

    async def fetch_watchlist_news(self, symbols: Optional[List[str]] = None, limit_per_symbol: int = 3) -> Dict[str, List[NewsArticle]]:
        """
        Fetch news for all symbols in watchlist concurrently.
        """
        target_symbols = symbols or settings.target_symbol_list
        tasks = [self.fetch_news_for_symbol(sym, limit=limit_per_symbol) for sym in target_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        market_news: Dict[str, List[NewsArticle]] = {}
        for sym, res in zip(target_symbols, results):
            if isinstance(res, list):
                market_news[sym] = res
            else:
                market_news[sym] = []

        return market_news

    async def _cache_articles(self, articles: List[NewsArticle]) -> None:
        """Cache articles to PostgreSQL news_cache table if connected."""
        if not db_manager.is_connected or not articles:
            return

        try:
            async with db_manager.connection() as conn:
                for art in articles:
                    for sym in art.symbols:
                        await conn.execute(
                            """
                            INSERT INTO news_cache (symbol, title, summary, source, url, published_at)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT DO NOTHING
                            """,
                            sym,
                            art.headline,
                            art.summary,
                            art.source,
                            art.url,
                            art.published_at,
                        )
        except Exception as e:
            logger.warning("Could not cache news to DB", error=str(e))


# Global News Fetcher singleton
news_fetcher = NewsFetcher()
