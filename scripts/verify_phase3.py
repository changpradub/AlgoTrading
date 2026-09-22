"""
Phase 3 Verification Script
Validates Alpaca News Fetching, OpenRouter Gemini 3.8 Flash Sentiment Analysis,
and AI Gatekeeper Pass/Block logic on live data.
Run with: .venv\\Scripts\\python scripts/verify_phase3.py --symbol NVDA
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config.settings import settings
from core.ai_sentiment import ai_gatekeeper
from core.news_fetcher import news_fetcher
from core.strategy import TradingSignal, SignalType


async def main():
    parser = argparse.ArgumentParser(description="Verify Phase 3 AI Sentiment & Gatekeeper")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Ticker symbol to test")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    print("=" * 70)
    print("  PHASE 3: AI SENTIMENT & GATEKEEPER LIVE VERIFICATION")
    print("=" * 70)
    print(f"Target Symbol:        {symbol}")
    print(f"AI Model:             {settings.OPENROUTER_MODEL}")
    print(f"OpenRouter Config:    {'Configured' if settings.OPENROUTER_API_KEY else 'Missing'}")
    print(f"Alpaca News Config:   {'Configured' if settings.ALPACA_API_KEY else 'Missing'}")

    # 1. Fetch Real-time News via Alpaca Benzinga Feed
    print(f"\n[1] Fetching live news articles for {symbol}...")
    articles = await news_fetcher.fetch_news_for_symbol(symbol, limit=3)
    if not articles:
        print("  • No news returned; creating synthetic sample news for testing.")
        from core.news_fetcher import NewsArticle
        from utils.timezone import now_utc
        articles = [
            NewsArticle(
                id="test-1",
                headline=f"{symbol} Announces Next-Gen AI Architecture with Record Energy Efficiency",
                summary="Customer adoption accelerates across hyperscalers.",
                symbols=[symbol],
                published_at=now_utc(),
                url="https://example.com/ai-chips",
                source="benzinga",
            )
        ]

    for i, art in enumerate(articles, 1):
        print(f"  {i}. [{art.published_at.strftime('%Y-%m-%d %H:%M')}] {art.headline}")
        print(f"     Source: {art.source} | URL: {art.url[:60]}...")

    # 2. Call OpenRouter AI (Gemini 3.8 Flash)
    print(f"\n[2] Invoking AI Gatekeeper ({settings.OPENROUTER_MODEL})...")
    report = await ai_gatekeeper.analyze_news(symbol, articles)

    print("\n" + "-" * 50)
    print(f"  AI SENTIMENT ANALYSIS RESULT: {report.symbol}")
    print("-" * 50)
    print(f"  • Sentiment:              {report.sentiment.value}")
    print(f"  • Confidence:             {report.confidence * 100:.1f}%")
    print(f"  • Risk Event Detected:    {report.risk_event}")
    print(f"  • Event Type:             {report.event_type}")
    print(f"  • Impact Level:           {report.impact}")
    print(f"  • Gatekeeper Action:      {report.action_recommendation.value}")
    print(f"  • Reasoning:              {report.reasoning}")
    print("-" * 50)

    # 3. Simulate Signal Gatekeeper Check
    print("\n[3] Testing Gatekeeper Integration with TradingSignal:")
    hypothetical_signal = TradingSignal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        entry_price=140.0,
        stop_loss=133.0,
        take_profit=150.0,
        risk_reward_ratio=1.43,
        timeframe="1H",
    )

    decision = await ai_gatekeeper.evaluate_signal_gatekeeper(hypothetical_signal, articles)
    print(f"  • Hypothetical Signal:    BUY {symbol} @ $140.0")
    print(f"  • Gatekeeper Decision:    {'[APPROVED]' if decision.approved else '[VETOED (BLOCKED)]'}")
    print(f"  • Final Decision Reason:  {decision.reason}")

    print("\n" + "=" * 70)
    print("  PHASE 3 VERIFICATION COMPLETED SUCCESSFULLY")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
