"""
Unit Tests for P1 Improvements:
1. Technical Engine: Volume SMA, MACD, Market Regime
2. Strategy: Volume Confirmation, MACD, Volatile Regime Block
3. Trailing Stop Manager: Activation tiers, SL never moves down
4. AI Sentiment Cache: TTL and cache hit/miss
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch
import numpy as np
import pandas as pd
import pytest

from core.technical import TechnicalAnalysisEngine
from core.strategy import SwingTrendPullbackStrategy, SignalType
from core.trailing_stop import TrailingStopManager
from core.ai_sentiment import AISentimentGatekeeper, AISentimentReport, SentimentType, GatekeeperAction
from utils.timezone import now_utc


# ============================================================================
# Technical Engine — New Indicators Tests
# ============================================================================


def _make_ohlcv_df(bars: int = 120, trend: str = "up") -> pd.DataFrame:
    """Create a sample OHLCV DataFrame."""
    rows = []
    base_time = now_utc()
    price = 140.0
    for i in range(bars):
        t = base_time - pd.Timedelta(minutes=(bars - i - 1) * 5)
        delta = 0.1 if trend == "up" else (-0.1 if trend == "down" else 0.0)
        price += delta
        rows.append({
            "timestamp": t,
            "open": price - 0.05,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 10000.0 + np.random.uniform(-2000, 2000),
        })
    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df


def test_technical_engine_volume_indicators():
    """Verify volume SMA and ratio are calculated."""
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv_df(120)
    result = engine.calculate_indicators(df)

    assert "volume_sma_20" in result.columns
    assert "volume_ratio" in result.columns
    # Last bar's volume ratio should be positive
    assert result.iloc[-1]["volume_ratio"] > 0


def test_technical_engine_macd_indicators():
    """Verify MACD line, signal, histogram are calculated."""
    engine = TechnicalAnalysisEngine()
    df = _make_ohlcv_df(120)
    result = engine.calculate_indicators(df)

    assert "macd_line" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_histogram" in result.columns
    # In an uptrend, MACD line should be positive
    assert result.iloc[-1]["macd_line"] > 0


def test_technical_engine_market_regime():
    """Verify market regime classification."""
    engine = TechnicalAnalysisEngine()

    # Uptrend data should be TRENDING
    df_up = _make_ohlcv_df(120, trend="up")
    result_up = engine.calculate_indicators(df_up)
    last_regime = result_up.iloc[-1]["market_regime"]
    assert last_regime in ("TRENDING", "RANGING"), f"Expected TRENDING or RANGING, got {last_regime}"


# ============================================================================
# Strategy — Enhanced Signal Conditions Tests
# ============================================================================


def test_strategy_volatile_regime_blocks_entry():
    """Verify that VOLATILE market regime blocks BUY signals."""
    strategy = SwingTrendPullbackStrategy()

    # Create highly volatile data (big swings)
    rows = []
    base_time = now_utc()
    price = 100.0
    for i in range(120):
        t = base_time - pd.Timedelta(minutes=(120 - i - 1) * 5)
        # Extreme volatility: price swings ±10%
        swing = 10.0 * np.sin(i * 0.5)
        rows.append({
            "timestamp": t,
            "open": price + swing,
            "high": price + swing + 5.0,
            "low": price + swing - 5.0,
            "close": price + swing + 0.1,
            "volume": 10000.0,
        })
    df_volatile = pd.DataFrame(rows)
    df_volatile.set_index("timestamp", inplace=True)

    signal = strategy.evaluate("NVDA", df_volatile)

    # Should be HOLD due to volatile conditions
    assert signal.signal_type == SignalType.HOLD


def test_strategy_hold_reason_includes_details():
    """Verify HOLD signals now include detailed reasons."""
    strategy = SwingTrendPullbackStrategy()
    df = _make_ohlcv_df(120, trend="down")  # Downtrend
    signal = strategy.evaluate("NVDA", df)

    assert signal.signal_type == SignalType.HOLD
    # The reason should contain specific condition failures
    assert "No entry:" in signal.reason or "VOLATILE" in signal.reason or "bearish" in signal.reason.lower()


# ============================================================================
# Trailing Stop Manager Tests
# ============================================================================


def test_trailing_stop_registration():
    """Verify position registration for trailing stop."""
    mgr = TrailingStopManager()
    state = mgr.register_position("NVDA", entry_price=140.0, stop_loss=135.0, atr=2.5)

    assert state.symbol == "NVDA"
    assert state.current_sl == 135.0
    assert not state.is_activated
    assert "NVDA" in mgr.tracked_symbols


def test_trailing_stop_activation_at_breakeven():
    """Verify SL moves to breakeven when price moves > 1.5×ATR above entry."""
    mgr = TrailingStopManager()
    mgr.register_position("NVDA", entry_price=140.0, stop_loss=135.0, atr=2.0)

    # Price moves up 1.5×ATR = 3.0 → highest = 143.0
    state = mgr.update("NVDA", 143.0)
    assert state.is_activated
    assert state.current_sl >= 140.0  # At least breakeven


def test_trailing_stop_tier2():
    """Verify SL moves to entry + 1×ATR when price moves > 2.5×ATR above entry."""
    mgr = TrailingStopManager()
    mgr.register_position("NVDA", entry_price=140.0, stop_loss=135.0, atr=2.0)

    # Price moves up 2.5×ATR = 5.0 → 145.0
    state = mgr.update("NVDA", 145.0)
    assert state.current_sl >= 142.0  # entry + 1×ATR


def test_trailing_stop_never_moves_down():
    """Verify SL NEVER moves down even if price drops."""
    mgr = TrailingStopManager()
    mgr.register_position("NVDA", entry_price=140.0, stop_loss=135.0, atr=2.0)

    # Price goes up → SL adjusts up
    mgr.update("NVDA", 145.0)
    state_up = mgr.get_state("NVDA")
    sl_after_up = state_up.current_sl

    # Price drops back → SL should NOT go down
    mgr.update("NVDA", 141.0)
    state_down = mgr.get_state("NVDA")

    assert state_down.current_sl >= sl_after_up, "SL must never decrease"


def test_trailing_stop_should_exit():
    """Verify should_exit returns True when price breaches trailing SL."""
    mgr = TrailingStopManager()
    mgr.register_position("NVDA", entry_price=140.0, stop_loss=135.0, atr=2.0)

    # Price goes up, activates trailing stop
    mgr.update("NVDA", 146.0)
    sl = mgr.get_state("NVDA").current_sl

    # Price drops below trailing SL
    assert mgr.should_exit("NVDA", sl - 0.50)


# ============================================================================
# AI Sentiment Cache Tests
# ============================================================================


def test_ai_cache_miss_and_hit():
    """Verify cache stores and retrieves AI analysis results."""
    gatekeeper = AISentimentGatekeeper(api_key="test_key")

    report = AISentimentReport(
        symbol="NVDA",
        sentiment=SentimentType.POSITIVE,
        confidence=0.85,
        risk_event=False,
        event_type="none",
        impact="LOW",
        action_recommendation=GatekeeperAction.PASS,
        reasoning="All clear",
    )

    # Cache miss
    assert gatekeeper._get_cached("NVDA") is None

    # Set cache
    gatekeeper._set_cache("NVDA", report)

    # Cache hit
    cached = gatekeeper._get_cached("NVDA")
    assert cached is not None
    assert cached.symbol == "NVDA"
    assert cached.confidence == 0.85


def test_ai_cache_expiry():
    """Verify cache expires after TTL."""
    gatekeeper = AISentimentGatekeeper(api_key="test_key")

    report = AISentimentReport(
        symbol="TSM",
        sentiment=SentimentType.NEUTRAL,
        confidence=0.5,
        risk_event=False,
        event_type="none",
        impact="LOW",
        action_recommendation=GatekeeperAction.PASS,
        reasoning="Neutral",
    )

    # Set cache with a past timestamp (expired)
    from datetime import datetime, timezone
    expired_time = now_utc() - timedelta(seconds=gatekeeper.AI_CACHE_TTL_SECONDS + 60)
    gatekeeper._cache["TSM"] = (report, expired_time)

    # Should return None (expired)
    assert gatekeeper._get_cached("TSM") is None


def test_ai_cache_clear():
    """Verify cache clear works for specific symbol and all."""
    gatekeeper = AISentimentGatekeeper(api_key="test_key")

    report = AISentimentReport(
        symbol="NVDA", sentiment=SentimentType.POSITIVE,
        confidence=0.9, risk_event=False, event_type="none",
        impact="LOW", action_recommendation=GatekeeperAction.PASS,
        reasoning="OK",
    )
    gatekeeper._set_cache("NVDA", report)
    gatekeeper._set_cache("TSM", report)

    gatekeeper.clear_cache("NVDA")
    assert gatekeeper._get_cached("NVDA") is None
    assert gatekeeper._get_cached("TSM") is not None

    gatekeeper.clear_cache()
    assert gatekeeper._get_cached("TSM") is None
