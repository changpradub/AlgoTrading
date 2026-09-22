"""
Unit tests for core/pre_market_scan.py
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.ai_sentiment import AISentimentReport, SentimentType, GatekeeperAction
from core.news_fetcher import NewsArticle
from core.pre_market_scan import PreMarketScanner


@pytest.mark.asyncio
async def test_pre_market_scan_detects_gap_warnings():
    scanner = PreMarketScanner()

    mock_report_danger = AISentimentReport(
        symbol="NVDA",
        sentiment=SentimentType.NEGATIVE,
        confidence=0.9,
        risk_event=True,
        event_type="regulatory_probe",
        impact="HIGH",
        action_recommendation=GatekeeperAction.BLOCK,
        reasoning="DOJ opens probe into antitrust practices.",
    )

    with patch("core.pre_market_scan.alpaca_trading_client.get_all_positions", new_callable=AsyncMock) as mock_pos, \
         patch("core.pre_market_scan.news_fetcher.fetch_news_for_symbol", new_callable=AsyncMock) as mock_fetch, \
         patch("core.pre_market_scan.ai_gatekeeper.analyze_news", new_callable=AsyncMock) as mock_analyze, \
         patch("core.pre_market_scan.dispatcher.notify_warning", new_callable=AsyncMock) as mock_notify:

        mock_pos.return_value = []
        mock_fetch.return_value = [MagicMock()] if False else []
        mock_analyze.return_value = mock_report_danger

        summary = await scanner.run_scan(custom_symbols=["NVDA"])

        assert summary.has_high_risk_events is True
        assert len(summary.gap_warnings) == 1
        assert summary.gap_warnings[0]["symbol"] == "NVDA"
        assert summary.gap_warnings[0]["impact"] == "HIGH"
        mock_notify.assert_awaited_once()
