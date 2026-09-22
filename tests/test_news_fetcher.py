"""
Unit tests for core/news_fetcher.py
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock, patch

from core.news_fetcher import NewsFetcher, NewsArticle


@pytest.fixture
def mock_news_data():
    class MockNewsSet:
        data = {
            "news": [
                {
                    "id": 12345,
                    "headline": "Nvidia Reports Record AI Chip Demand",
                    "summary": "Q4 earnings surge 120% YoY driven by H100 and Blackwell GPUs.",
                    "symbols": ["NVDA"],
                    "created_at": datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc),
                    "url": "https://example.com/news/12345",
                    "source": "benzinga",
                }
            ]
        }
    return MockNewsSet()


@pytest.mark.asyncio
async def test_fetch_news_success(mock_news_data):
    fetcher = NewsFetcher()

    with patch.object(fetcher, "_ensure_client") as mock_client:
        mock_client.return_value.get_news.return_value = mock_news_data
        articles = await fetcher.fetch_news_for_symbol("NVDA", limit=1)

        assert len(articles) == 1
        art = articles[0]
        assert art.id == "12345"
        assert art.headline == "Nvidia Reports Record AI Chip Demand"
        assert "NVDA" in art.symbols
        assert art.source == "benzinga"


@pytest.mark.asyncio
async def test_fetch_news_empty():
    fetcher = NewsFetcher()

    class EmptyNewsSet:
        data = {"news": []}

    with patch.object(fetcher, "_ensure_client") as mock_client:
        mock_client.return_value.get_news.return_value = EmptyNewsSet()
        articles = await fetcher.fetch_news_for_symbol("UNKNOWN", limit=1)
        assert len(articles) == 0
