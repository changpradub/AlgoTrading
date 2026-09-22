"""
Unit tests for core/ai_sentiment.py
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch

from core.ai_sentiment import (
    AISentimentGatekeeper,
    GatekeeperAction,
    SentimentType,
)
from core.news_fetcher import NewsArticle
from core.strategy import TradingSignal, SignalType


@pytest.fixture
def sample_article():
    return NewsArticle(
        id="1",
        headline="TSMC Facing Major Factory Earthquake Disruption",
        summary="Key 3nm fab halted after seismic event, impacting Q3 shipments.",
        symbols=["TSM"],
        published_at=datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc),
        url="https://example.com/1",
        source="benzinga",
    )


@pytest.fixture
def sample_buy_signal():
    return TradingSignal(
        symbol="TSM",
        signal_type=SignalType.BUY,
        entry_price=175.0,
        stop_loss=168.0,
        take_profit=189.0,
        risk_reward_ratio=2.0,
        timeframe="1H",
    )


def test_clean_json_parsing():
    gatekeeper = AISentimentGatekeeper()

    # Raw JSON
    raw = '{"symbol": "NVDA", "sentiment": "POSITIVE", "confidence": 0.9, "risk_event": false, "impact": "LOW", "action_recommendation": "PASS", "reasoning": "Strong earnings."}'
    parsed = gatekeeper._clean_json_response(raw)
    assert parsed["symbol"] == "NVDA"
    assert parsed["action_recommendation"] == "PASS"

    # Markdown fenced JSON
    markdown_json = '```json\n{"symbol": "NVDA", "action_recommendation": "BLOCK"}\n```'
    parsed_md = gatekeeper._clean_json_response(markdown_json)
    assert parsed_md["action_recommendation"] == "BLOCK"


@pytest.mark.asyncio
async def test_gatekeeper_vetoes_on_block_recommendation(sample_article, sample_buy_signal):
    gatekeeper = AISentimentGatekeeper(api_key="mock_key")

    mock_response_json = {
        "symbol": "TSM",
        "sentiment": "NEGATIVE",
        "confidence": 0.95,
        "risk_event": True,
        "event_type": "disaster_disruption",
        "impact": "HIGH",
        "action_recommendation": "BLOCK",
        "reasoning": "Major fab damage causes supply disruption.",
    }

    with patch.object(gatekeeper, "analyze_news", new_callable=AsyncMock) as mock_analyze:
        from core.ai_sentiment import AISentimentReport
        mock_analyze.return_value = AISentimentReport(
            symbol="TSM",
            sentiment=SentimentType.NEGATIVE,
            confidence=0.95,
            risk_event=True,
            event_type="disaster_disruption",
            impact="HIGH",
            action_recommendation=GatekeeperAction.BLOCK,
            reasoning="Major fab damage causes supply disruption.",
        )

        decision = await gatekeeper.evaluate_signal_gatekeeper(sample_buy_signal, [sample_article])

        # Vetoed!
        assert decision.approved is False
        assert decision.action == GatekeeperAction.BLOCK
        assert "AI Gatekeeper BLOCKED trade" in decision.reason


@pytest.mark.asyncio
async def test_gatekeeper_approves_on_pass_recommendation(sample_article, sample_buy_signal):
    gatekeeper = AISentimentGatekeeper(api_key="mock_key")

    with patch.object(gatekeeper, "analyze_news", new_callable=AsyncMock) as mock_analyze:
        from core.ai_sentiment import AISentimentReport
        mock_analyze.return_value = AISentimentReport(
            symbol="TSM",
            sentiment=SentimentType.POSITIVE,
            confidence=0.85,
            risk_event=False,
            event_type="none",
            impact="LOW",
            action_recommendation=GatekeeperAction.PASS,
            reasoning="Solid demand trends.",
        )

        decision = await gatekeeper.evaluate_signal_gatekeeper(sample_buy_signal, [sample_article])

        # Approved!
        assert decision.approved is True
        assert decision.action == GatekeeperAction.PASS
